"""Extended daily digest and report helpers."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentProvider,
    PaymentStatus,
    Plan,
    ProvisioningLog,
    Subscription,
    SubscriptionStatus,
    SupportTicket,
    TelegramUser,
    TicketStatus,
)
from bot.services.admin_ops import build_ops_snapshot, health_badge
from bot.services import bot_content


async def build_daily_digest(session: AsyncSession) -> str:
    snapshot = await build_ops_snapshot(session)
    now = datetime.now(UTC)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)
    yesterday = now - timedelta(days=1)

    counts = (
        await session.execute(
            select(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.status == SubscriptionStatus.ACTIVE)
                .scalar_subquery(),
                select(func.count())
                .select_from(TelegramUser)
                .where(TelegramUser.created_at >= since_24h)
                .scalar_subquery(),
                select(func.count())
                .select_from(TelegramUser)
                .where(TelegramUser.created_at >= since_7d)
                .scalar_subquery(),
                select(func.count())
                .select_from(Order)
                .where(Order.created_at >= since_24h)
                .scalar_subquery(),
                select(func.count())
                .select_from(Order)
                .where(Order.status == OrderStatus.COMPLETED, Order.updated_at >= since_24h)
                .scalar_subquery(),
                select(func.count())
                .select_from(Order)
                .where(Order.status == OrderStatus.FAILED, Order.updated_at >= since_24h)
                .scalar_subquery(),
                select(func.coalesce(func.sum(Payment.amount_toman), 0))
                .where(
                    Payment.status == PaymentStatus.COMPLETED,
                    Payment.created_at >= since_24h,
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.recharge_package_id.isnot(None),
                    Payment.status == PaymentStatus.COMPLETED,
                    Payment.created_at >= since_24h,
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.status == SubscriptionStatus.EXPIRED,
                    Subscription.expires_at >= yesterday,
                    Subscription.expires_at < now,
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.expires_at >= now,
                    Subscription.expires_at < now + timedelta(days=1),
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.expires_at >= now,
                    Subscription.expires_at < now + timedelta(days=3),
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.provider == PaymentProvider.C2C,
                    Payment.status == PaymentStatus.COMPLETED,
                    Payment.created_at >= since_24h,
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.provider == PaymentProvider.C2C,
                    Payment.status == PaymentStatus.REJECTED,
                    Payment.created_at >= since_24h,
                )
                .scalar_subquery(),
                select(func.count())
                .select_from(ProvisioningLog)
                .where(ProvisioningLog.ok.is_(False), ProvisioningLog.created_at >= since_24h)
                .scalar_subquery(),
                select(func.count())
                .select_from(SupportTicket)
                .where(SupportTicket.status == TicketStatus.OPEN)
                .scalar_subquery(),
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.is_trial.is_(True),
                    Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.LIMITED]),
                )
                .scalar_subquery(),
            )
        )
    ).one()
    (
        active_subs,
        new_users_24h,
        new_users_7d,
        orders_created,
        orders_completed,
        orders_failed,
        revenue_24h,
        wallet_recharges,
        expired_yesterday,
        expiring_today,
        expiring_3d,
        c2c_approved,
        c2c_rejected,
        prov_fail,
        open_tickets,
        trial_active,
    ) = (int(x or 0) for x in counts)

    top_plans = (
        await session.execute(
            select(Plan.name_fa, func.count(Order.id))
            .join(Order, Order.plan_id == Plan.id)
            .where(Order.status == OrderStatus.COMPLETED, Order.created_at >= since_24h)
            .group_by(Plan.id, Plan.name_fa)
            .order_by(func.count(Order.id).desc())
            .limit(3)
        )
    ).all()
    top_text = ", ".join(f"{n}({c})" for n, c in top_plans) if top_plans else "—"

    hb = health_badge
    return (
        "<b>📊 گزارش روزانه NoranX</b>\n"
        f"<i>{now.strftime('%Y-%m-%d %H:%M UTC')}</i>\n\n"
        f"<b>کاربران</b>\n"
        f"• جدید ۲۴س: <code>{new_users_24h}</code> | ۷روز: <code>{new_users_7d}</code>\n\n"
        f"<b>اشتراک‌ها</b>\n"
        f"• فعال: <code>{active_subs}</code> | تست فعال: <code>{trial_active}</code>\n"
        f"• منقضی امروز: <code>{expiring_today}</code> | ۳روز: <code>{expiring_3d}</code>\n"
        f"• منقضی دیروز: <code>{expired_yesterday}</code>\n\n"
        f"<b>فروش ۲۴س</b>\n"
        f"• سفارش: <code>{orders_created}</code> تکمیل: <code>{orders_completed}</code> "
        f"ناموفق: <code>{orders_failed}</code>\n"
        f"• درآمد: <code>{revenue_24h:,}</code> تومان\n"
        f"• شارژ کیف پول: <code>{wallet_recharges}</code>\n"
        f"• پرفروش: {top_text}\n\n"
        f"<b>C2C</b> تأیید: <code>{c2c_approved}</code> رد: <code>{c2c_rejected}</code>\n"
        f"<b>Provisioning خطا:</b> <code>{prov_fail}</code>\n"
        f"<b>تیکت باز:</b> <code>{open_tickets}</code>\n\n"
        f"<b>صندوق عملیات</b>\n"
        f"• C2C بررسی: <code>{snapshot.c2c_review}</code> | منتظر: <code>{snapshot.c2c_waiting}</code>\n"
        f"• سفارش گیرکرده/ناموفق: <code>{snapshot.stuck_orders}</code> / <code>{snapshot.failed_orders}</code>\n"
        f"• Limiter drift: <code>{snapshot.limiter_drift}</code>\n"
        f"• {hb(snapshot.marzban_ok)} Marzban  {hb(snapshot.device_ok)} Device  {hb(snapshot.ip_ok)} IP\n\n"
        f"<b>نیاز به اقدام:</b> <code>{snapshot.total_actionable}</code>"
    )


async def get_digest_schedule(session: AsyncSession) -> tuple[bool, int, int]:
    enabled = (await bot_content.get_setting(session, "ops_digest_enabled")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    try:
        hour = int(await bot_content.get_setting(session, "ops_digest_hour"))
    except ValueError:
        hour = 9
    try:
        minute = int(await bot_content.get_setting(session, "ops_digest_minute"))
    except ValueError:
        minute = 0
    return enabled, hour, minute
