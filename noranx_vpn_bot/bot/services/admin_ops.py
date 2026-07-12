import asyncio
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentProvider,
    PaymentStatus,
    ProvisioningLog,
    Subscription,
    SubscriptionStatus,
    SupportTicket,
    TicketStatus,
)
from bot.services.registry import get_ip_limiter, get_marzban, get_sync_service


@dataclass
class OpsSnapshot:
    c2c_review: int
    c2c_waiting: int
    open_tickets: int
    stuck_orders: int
    failed_orders: int
    limiter_drift: int
    marzban_ok: bool
    ip_ok: bool

    @property
    def total_actionable(self) -> int:
        return (
            self.c2c_review
            + self.c2c_waiting
            + self.open_tickets
            + self.stuck_orders
            + self.failed_orders
            + (1 if not (self.marzban_ok and self.ip_ok) else 0)
            + (1 if self.limiter_drift > 0 else 0)
        )

    @property
    def health_ok(self) -> bool:
        return self.marzban_ok and self.ip_ok


def badge(count: int) -> str:
    return f" ({count})" if count > 0 else ""


def health_badge(ok: bool) -> str:
    return "🟢" if ok else "🔴"


async def _ops_counts(session: AsyncSession) -> tuple[int, int, int, int, int]:
    row = (
        await session.execute(
            select(
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.provider == PaymentProvider.C2C,
                    Payment.status == PaymentStatus.PENDING_REVIEW,
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.provider == PaymentProvider.C2C,
                    Payment.status == PaymentStatus.PENDING,
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(SupportTicket)
                .where(SupportTicket.status != TicketStatus.CLOSED)
                .scalar_subquery(),
                select(func.count())
                .select_from(Order)
                .where(Order.status == OrderStatus.PROVISIONING)
                .scalar_subquery(),
                select(func.count())
                .select_from(Order)
                .where(Order.status == OrderStatus.FAILED)
                .scalar_subquery(),
            )
        )
    ).one()
    return tuple(int(x or 0) for x in row)


async def build_ops_snapshot(session: AsyncSession) -> OpsSnapshot:
    c2c_review, c2c_waiting, open_tickets, stuck_orders, failed_orders = await _ops_counts(session)

    marzban = get_marzban()
    ip_lim = get_ip_limiter()
    (m_ok, _, _), (i_ok, _, _) = await asyncio.gather(
        marzban.health_check(),
        ip_lim.health_check(),
    )
    drift = await get_sync_service().count_limiter_drift(session)

    return OpsSnapshot(
        c2c_review=c2c_review,
        c2c_waiting=c2c_waiting,
        open_tickets=open_tickets,
        stuck_orders=stuck_orders,
        failed_orders=failed_orders,
        limiter_drift=drift,
        marzban_ok=m_ok,
        ip_ok=i_ok,
    )


def format_ops_inbox_text(snapshot: OpsSnapshot) -> str:
    hb = health_badge
    return (
        "<b>📥 صندوق عملیات</b>\n\n"
        f"• 💳 C2C بررسی: <code>{snapshot.c2c_review}</code> | منتظر رسید: <code>{snapshot.c2c_waiting}</code>\n"
        f"• 🎫 تیکت باز: <code>{snapshot.open_tickets}</code>\n"
        f"• 📋 سفارش گیرکرده/ناموفق: <code>{snapshot.stuck_orders}</code> / <code>{snapshot.failed_orders}</code>\n"
        f"• 🔒 Limiter drift: <code>{snapshot.limiter_drift}</code>\n"
        f"• {hb(snapshot.marzban_ok)} Marzban  {hb(snapshot.ip_ok)} IP\n\n"
        f"<b>نیاز به اقدام:</b> <code>{snapshot.total_actionable}</code>"
    )


async def build_quick_stats(session: AsyncSession) -> str:
    snapshot = await build_ops_snapshot(session)
    return (
        "<b>وضعیت سریع</b>\n"
        f"• 💳 C2C بررسی: <code>{snapshot.c2c_review}</code> | منتظر رسید: <code>{snapshot.c2c_waiting}</code>\n"
        f"• 🎫 تیکت باز: <code>{snapshot.open_tickets}</code>\n"
        f"• 📋 سفارش گیرکرده/ناموفق: <code>{snapshot.stuck_orders}</code> / <code>{snapshot.failed_orders}</code>\n"
        f"• 🔒 Limiter drift: <code>{snapshot.limiter_drift}</code>\n"
        f"• {health_badge(snapshot.marzban_ok)} Marzban  "
        f"{health_badge(snapshot.ip_ok)} IP"
    )


async def build_daily_digest(session: AsyncSession) -> str:
    from datetime import UTC, datetime, timedelta

    snapshot = await build_ops_snapshot(session)
    now = datetime.now(UTC)
    today_end = now + timedelta(days=1)
    three_days = now + timedelta(days=3)
    since = now - timedelta(hours=24)

    digest_row = (
        await session.execute(
            select(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.status == SubscriptionStatus.ACTIVE)
                .scalar_subquery(),
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.expires_at >= now,
                    Subscription.expires_at < today_end,
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.expires_at >= now,
                    Subscription.expires_at < three_days,
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.provider == PaymentProvider.C2C,
                    Payment.status == PaymentStatus.COMPLETED,
                    Payment.created_at >= since,
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.provider == PaymentProvider.C2C,
                    Payment.status == PaymentStatus.REJECTED,
                    Payment.created_at >= since,
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(ProvisioningLog)
                .where(ProvisioningLog.ok.is_(False), ProvisioningLog.created_at >= since)
                .scalar_subquery(),
            )
        )
    ).one()
    active_subs, expiring_today, expiring_3d, c2c_approved, c2c_rejected, prov_fail = (
        int(x or 0) for x in digest_row
    )

    return (
        f"<b>📊 گزارش روزانه</b> — {now.strftime('%Y-%m-%d')}\n\n"
        f"• اشتراک فعال: <code>{active_subs}</code>\n"
        f"• منقضی امروز: <code>{expiring_today}</code> | ۳ روز: <code>{expiring_3d}</code>\n"
        f"• C2C ۲۴س: تأیید <code>{c2c_approved}</code> / رد <code>{c2c_rejected}</code>\n"
        f"• Provisioning fail ۲۴س: <code>{prov_fail}</code>\n"
        f"• C2C در صف: <code>{snapshot.c2c_review}</code> | تیکت: <code>{snapshot.open_tickets}</code>\n"
        f"• Limiter drift: <code>{snapshot.limiter_drift}</code>\n"
        f"• {health_badge(snapshot.marzban_ok)} Marzban  "
        f"{health_badge(snapshot.ip_ok)} IP"
    )
