from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminAuditLog, Order, OrderStatus, Payment, PaymentStatus, Plan
from bot.services.orders import OrderService


@dataclass
class RetryResult:
    ok: bool
    message: str
    subscriptions: list = None

    def __post_init__(self) -> None:
        if self.subscriptions is None:
            self.subscriptions = []


def can_retry_order(order: Order, has_completed_payment: bool) -> tuple[bool, str]:
    if order.status not in (OrderStatus.PROVISIONING, OrderStatus.FAILED):
        return False, f"وضعیت سفارش قابل تلاش مجدد نیست: {order.status.value}"
    if not has_completed_payment:
        return False, "پرداخت تکمیل‌شده برای این سفارش یافت نشد."
    return True, ""


async def retry_order(
    session: AsyncSession,
    order_id: int,
    order_service: OrderService,
    admin_telegram_id: int,
) -> RetryResult:
    order = await session.get(Order, order_id)
    if not order:
        return RetryResult(False, "سفارش یافت نشد.")

    paid = await session.scalar(
        select(Payment.id)
        .where(
            Payment.order_id == order_id,
            Payment.status == PaymentStatus.COMPLETED,
        )
        .limit(1)
    )
    ok, reason = can_retry_order(order, paid is not None)
    if not ok:
        return RetryResult(False, reason)

    plan = await session.get(Plan, order.plan_id)
    if not plan:
        return RetryResult(False, "پلن سفارش یافت نشد.")

    order.status = OrderStatus.PAID
    await session.flush()
    subs = await order_service.fulfill_order(session, order, plan, order.user_id)
    await session.flush()

    session.add(
        AdminAuditLog(
            admin_telegram_id=admin_telegram_id,
            action="order_retry",
            details=f"order_id={order_id} status={order.status.value} subs={len(subs)}",
        )
    )

    if order.status == OrderStatus.COMPLETED:
        return RetryResult(True, f"✅ سفارش #{order_id} با موفقیت تکمیل شد.", subs)
    return RetryResult(False, f"تلاش مجدد ناموفق — وضعیت: {order.status.value}")
