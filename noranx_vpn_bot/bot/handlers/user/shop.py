from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.enums import ParseMode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import Plan
from bot.keyboards.user import (
    CHECKOUT_CRYPTO_HINT,
    checkout_kb,
    plans_kb,
    username_choice_kb,
)
from bot.services.marzban import MarzbanError, MarzbanService
from bot.services.username_availability import is_username_available
from bot.utils.logging import get_logger
from bot.services.discount import DiscountService
from bot.services.orders import OrderService
from bot.services.payment.c2c_base import get_c2c_adapter
from bot.services.payment.c2c_review import cancel_keyboard
from bot.services.payment.c2c_utils import build_c2c_metadata, c2c_available
from bot.services.payment.wallet import WalletService
from bot.services.referral import ReferralService
from bot.states import PaymentStates, ShopStates
from bot.keyboards.common import cancel_fsm_kb
from bot.services import bot_content
from bot.utils.formatting import format_toman

router = Router()
discount_service = DiscountService()
wallet_service = WalletService()
logger = get_logger("shop")

CUSTOM_USERNAME_PROMPT = (
    "نام کاربری دلخواه را وارد کنید (۳–۳۲ کاراکتر، a-z، 0-9، _):"
)
MARZBAN_UNAVAILABLE_MSG = (
    "سرویس موقتاً در دسترس نیست. لطفاً چند لحظه بعد دوباره تلاش کنید."
)


async def _reply_username_retry(message: Message, err: str) -> None:
    await message.answer(
        f"❌ {err}\n\n{CUSTOM_USERNAME_PROMPT}",
        reply_markup=cancel_fsm_kb(),
    )


async def _show_checkout(callback: CallbackQuery, order, plan) -> None:
    total = format_toman(order.total_toman)
    username_line = ""
    if order.preferred_username:
        username_line = f"\nنام کاربری: <code>{order.preferred_username}</code>\n"
    await callback.message.edit_text(
        f"📋 سفارش #{order.id}\n"
        f"پلن: {plan.name_fa}\n"
        f"مبلغ: {total}\n"
        f"{username_line}\n"
        f"{CHECKOUT_CRYPTO_HINT}",
        reply_markup=checkout_kb(order.id),
        parse_mode="HTML",
    )


async def _show_username_choice(callback: CallbackQuery, order, plan) -> None:
    await callback.message.edit_text(
        f"📋 سفارش #{order.id}\n"
        f"پلن: {plan.name_fa}\n"
        f"مبلغ: {format_toman(order.total_toman)}\n\n"
        "نام کاربری سرویس را انتخاب کنید:",
        reply_markup=username_choice_kb(order.id),
    )


def _get_services() -> OrderService:
    from bot.services.ip_limiter import IpLimiterService
    from bot.services.marzban import MarzbanService
    from bot.services.provisioner import ProvisionerService

    s = get_settings()
    return OrderService(
        wallet_service,
        discount_service,
        ProvisionerService(s, MarzbanService(s), IpLimiterService(s)),
        ReferralService(s),
    )


@router.callback_query(F.data == "menu:shop")
async def shop_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    plans = (
        await session.scalars(
            select(Plan).where(Plan.is_active).order_by(Plan.sort_order, Plan.device_count)
        )
    ).all()
    header = await bot_content.get_shop_header(session)
    await callback.message.edit_text(
        header,
        reply_markup=plans_kb(list(plans)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop:plan:"))
async def shop_plan(callback: CallbackQuery, session: AsyncSession) -> None:
    slug = callback.data.split(":")[-1]
    plan = await session.scalar(select(Plan).where(Plan.slug == slug))
    if not plan:
        await callback.answer("پلن یافت نشد.", show_alert=True)
        return

    from bot.db.models import TelegramUser

    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not user:
        await callback.answer("ابتدا /start بزنید.", show_alert=True)
        return

    svc = _get_services()
    order = await svc.create_order(session, user.id, plan, 1)
    if order.quantity == 1 and not order.is_renewal:
        await _show_username_choice(callback, order, plan)
    else:
        await _show_checkout(callback, order, plan)
    await callback.answer()


@router.callback_query(F.data.startswith("shop:uname:default:"))
async def shop_username_default(callback: CallbackQuery, session: AsyncSession) -> None:
    from bot.db.models import Order, TelegramUser

    order_id = int(callback.data.split(":")[-1])
    order = await session.get(Order, order_id)
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not order or not user or order.user_id != user.id:
        await callback.answer("سفارش نامعتبر.", show_alert=True)
        return
    order.preferred_username = None
    await session.flush()
    plan = await session.get(Plan, order.plan_id)
    logger.info("username_pick order_id=%s choice=default", order.id)
    await _show_checkout(callback, order, plan)
    await callback.answer()


@router.callback_query(F.data.startswith("shop:uname:custom:"))
async def shop_username_custom_prompt(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    from bot.db.models import Order, TelegramUser

    order_id = int(callback.data.split(":")[-1])
    order = await session.get(Order, order_id)
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not order or not user or order.user_id != user.id:
        await callback.answer("سفارش نامعتبر.", show_alert=True)
        return
    await state.set_state(ShopStates.waiting_custom_username)
    await state.update_data(order_id=order_id)
    await callback.message.answer(
        CUSTOM_USERNAME_PROMPT,
        reply_markup=cancel_fsm_kb(),
    )
    await callback.answer()


@router.message(ShopStates.waiting_custom_username)
async def shop_username_custom_apply(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    from bot.db.models import Order, Plan, TelegramUser

    data = await state.get_data()
    order_id = data.get("order_id")

    order = await session.get(Order, order_id)
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == message.from_user.id)
    )
    if not order or not user or order.user_id != user.id:
        await state.clear()
        await message.answer("سفارش یافت نشد.")
        return

    settings = get_settings()
    marzban = MarzbanService(settings)
    try:
        ok, err, normalized = await is_username_available(
            session, marzban, message.text or ""
        )
    except MarzbanError:
        await _reply_username_retry(message, MARZBAN_UNAVAILABLE_MSG)
        return

    if not ok or not normalized:
        logger.info("username_pick_retry order_id=%s reason=%s", order_id, err)
        await _reply_username_retry(message, err or "نام کاربری نامعتبر است.")
        return

    await state.clear()
    order.preferred_username = normalized
    await session.flush()
    plan = await session.get(Plan, order.plan_id)
    logger.info("username_pick order_id=%s choice=custom value=%s", order.id, normalized)
    await message.answer(
        f"📋 سفارش #{order.id}\n"
        f"پلن: {plan.name_fa}\n"
        f"نام کاربری: <code>{normalized}</code>\n"
        f"مبلغ: {format_toman(order.total_toman)}\n\n"
        f"{CHECKOUT_CRYPTO_HINT}",
        reply_markup=checkout_kb(order.id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("shop:discount:"))
async def shop_discount_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[-1])
    await state.set_state(ShopStates.waiting_discount)
    await state.update_data(order_id=order_id)
    await callback.message.answer("کد تخفیف را وارد کنید:", reply_markup=cancel_fsm_kb())
    await callback.answer()


@router.message(ShopStates.waiting_discount)
async def shop_apply_discount(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    order_id = data.get("order_id")
    await state.clear()

    from bot.db.models import Order, TelegramUser

    order = await session.get(Order, order_id)
    if not order:
        await message.answer("سفارش یافت نشد.")
        return
    plan = await session.get(Plan, order.plan_id)
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == message.from_user.id)
    )
    subtotal = plan.price_toman * order.quantity
    dc, err = await discount_service.validate(
        session, message.text.strip(), user.id, plan.slug, subtotal
    )
    if not dc:
        await message.answer(err)
        return
    order.total_toman = discount_service.apply(dc, subtotal)
    order.discount_id = dc.id
    await session.flush()
    await message.answer(
        f"✅ تخفیف اعمال شد.\nمبلغ نهایی: {format_toman(order.total_toman)}\n\n"
        f"{CHECKOUT_CRYPTO_HINT}",
        reply_markup=checkout_kb(order.id),
    )


@router.callback_query(F.data.startswith("pay:wallet:"))
async def pay_wallet(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[-1])
    from bot.db.models import Order, TelegramUser

    order = await session.get(Order, order_id)
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not order or not user or order.user_id != user.id:
        await callback.answer("سفارش نامعتبر.", show_alert=True)
        return

    svc = _get_services()
    if not await svc.pay_with_wallet(session, order, user.id):
        await callback.answer("موجودی کیف پول کافی نیست.", show_alert=True)
        return

    plan = await session.get(Plan, order.plan_id)
    subs = await svc.fulfill_order(session, order, plan, user.id)
    await _deliver_subscriptions(callback, subs, order, session)
    await callback.answer()


@router.callback_query(F.data.startswith("pay:c2c:"))
async def pay_c2c(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    order_id = int(callback.data.split(":")[-1])
    from bot.db.models import Order, Payment, PaymentProvider, PaymentStatus, TelegramUser

    settings = get_settings()
    if not c2c_available(settings):
        await callback.answer("پرداخت کارت به کارت فعال نیست.", show_alert=True)
        return

    order = await session.get(Order, order_id)
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not order or not user or order.user_id != user.id:
        await callback.answer("سفارش نامعتبر.", show_alert=True)
        return
    from bot.db.models import OrderStatus

    if order.status != OrderStatus.PENDING:
        await callback.answer("این سفارش دیگر قابل پرداخت نیست.", show_alert=True)
        return

    c2c = get_c2c_adapter(settings)
    intent = await c2c.create_order_payment(user.id, order.id, order.total_toman)
    payment = Payment(
        order_id=order.id,
        user_id=user.id,
        provider=PaymentProvider.C2C,
        external_id=intent.external_id,
        amount_toman=order.total_toman,
        status=PaymentStatus.PENDING,
        metadata_json=build_c2c_metadata(
            intent.external_id, order.total_toman, order_id=order.id
        ),
    )
    session.add(payment)
    await session.flush()

    await state.set_state(PaymentStates.waiting_c2c_receipt)
    await state.update_data(payment_id=payment.id)

    await callback.message.answer(
        intent.instructions,
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(payment.id),
    )
    await callback.answer()


async def _deliver_subscriptions(
    callback: CallbackQuery, subs: list, order, session: AsyncSession
) -> None:
    from bot.db.models import TelegramUser
    from bot.services.payment.completion import notify_order_fulfilled

    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if user:
        await notify_order_fulfilled(callback.bot, session, user, order, subs)
