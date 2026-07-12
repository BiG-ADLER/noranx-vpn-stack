from dataclasses import dataclass, field

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    Plan,
    Subscription,
    TelegramUser,
    WalletTxType,
)
from bot.services.orders import OrderService
from bot.services.payment.wallet import WalletService
from bot.utils.logging import get_logger
from bot.utils.subscription_delivery import send_subscription_details

logger = get_logger("c2c")


@dataclass
class CompleteResult:
    already_completed: bool = False
    order_fulfilled: bool = False
    wallet_credited: bool = False
    subscriptions: list[Subscription] = field(default_factory=list)
    error: str | None = None


async def complete_payment(
    session: AsyncSession,
    payment: Payment,
    *,
    order_service: OrderService,
    wallet: WalletService | None = None,
    source: str = "unknown",
) -> CompleteResult:
    if payment.status == PaymentStatus.COMPLETED:
        return CompleteResult(already_completed=True)

    if payment.status not in (
        PaymentStatus.PENDING,
        PaymentStatus.PENDING_REVIEW,
    ):
        return CompleteResult(error=f"invalid_status:{payment.status.value}")

    wallet = wallet or WalletService()
    result = CompleteResult()

    if payment.order_id:
        order = await session.get(Order, payment.order_id)
        if not order:
            return CompleteResult(error="order_not_found")
        if order.status not in (OrderStatus.PENDING, OrderStatus.PAID):
            return CompleteResult(error=f"order_status:{order.status.value}")

        order.status = OrderStatus.PAID
        plan = await session.get(Plan, order.plan_id)
        if not plan:
            return CompleteResult(error="plan_not_found")

        subs = await order_service.fulfill_order(session, order, plan, payment.user_id)
        payment.status = PaymentStatus.COMPLETED
        await session.flush()
        result.order_fulfilled = True
        result.subscriptions = [s for s in subs if s]
        logger.info(
            "payment completed source=%s payment_id=%s order_id=%s subs=%s",
            source,
            payment.id,
            order.id,
            len(result.subscriptions),
        )
        try:
            from bot.db.models import TelegramUser
            from bot.main import get_bot_instance
            from bot.services.notification_hub import NotificationHub

            bot = get_bot_instance()
            user = await session.get(TelegramUser, payment.user_id)
            if bot and user:
                hub = NotificationHub(bot, session)
                await hub.notify_purchase(
                    user.telegram_id, payment.amount_toman, f"order #{order.id}"
                )
        except Exception:
            pass
        return result

    if payment.recharge_package_id:
        await wallet.credit(
            session,
            payment.user_id,
            payment.amount_toman,
            WalletTxType.DEPOSIT,
            reference=payment.external_id,
            note=f"c2c recharge ({source})",
        )
        payment.status = PaymentStatus.COMPLETED
        await session.flush()
        result.wallet_credited = True
        logger.info(
            "wallet credited source=%s payment_id=%s amount=%s",
            source,
            payment.id,
            payment.amount_toman,
        )
        return result

    return CompleteResult(error="no_target")


async def notify_order_fulfilled(
    bot: Bot,
    session: AsyncSession,
    user: TelegramUser,
    order: Order,
    subs: list[Subscription],
    *,
    header: str | None = None,
) -> None:
    if not subs:
        try:
            await bot.send_message(
                user.telegram_id,
                "❌ خطا در فعال‌سازی. با پشتیبانی تماس بگیرید.",
            )
        except Exception:
            pass
        return

    title = header or f"✅ سفارش #{order.id} با موفقیت انجام شد!"
    try:
        await bot.send_message(user.telegram_id, title)
    except Exception:
        pass

    for i, sub in enumerate(subs, 1):
        await send_subscription_details(
            bot,
            user.telegram_id,
            marzban_username=sub.marzban_username,
            subscription_url=sub.subscription_url,
            device_limit=sub.device_limit,
            account_index=i,
        )


async def notify_wallet_credited(
    bot: Bot,
    user: TelegramUser,
    amount_toman: int,
    *,
    header: str | None = None,
) -> None:
    amount = f"{amount_toman:,}".replace(",", "٬")
    msg = header or f"✅ کیف پول شما {amount} تومان شارژ شد."
    try:
        await bot.send_message(user.telegram_id, msg)
    except Exception:
        pass
