import asyncio
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from bot.config import get_settings
from bot.db.models import (
    Order,
    OrderStatus,
    Subscription,
    SubscriptionStatus,
    TelegramUser,
)
from bot.db.session import async_session_factory
from bot.jobs import registry as job_registry
from bot.services.notification_hub import NotificationHub
from bot.services.registry import (
    get_ip_limiter,
    get_marzban,
    get_sync_service,
)
from bot.services.reports import build_daily_digest, get_digest_schedule
from bot.services.traffic_anomaly import TrafficAnomalyService
from bot.utils.logging import get_logger

logger = get_logger("scheduler")


def _alert_kb(buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=cb)] for label, cb in buttons
        ]
    )


async def _map_limited(semaphore: asyncio.Semaphore, items, coro_fn):
    async def run(item):
        async with semaphore:
            return await coro_fn(item)

    return await asyncio.gather(*(run(i) for i in items), return_exceptions=True)


async def _safe_job(name: str, coro) -> None:
    try:
        await coro()
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    settings = get_settings()

    async def sync_subscriptions() -> None:
        s = get_settings()
        sync = get_sync_service()
        sem = asyncio.Semaphore(s.scheduler_max_concurrency)
        async with async_session_factory() as session:
            subs = (
                await session.scalars(
                    select(Subscription).where(
                        Subscription.status.in_(
                            [SubscriptionStatus.ACTIVE, SubscriptionStatus.LIMITED]
                        )
                    )
                )
            ).all()

            async def fetch_mb(sub: Subscription):
                mb = await sync._marzban.get_user(sub.marzban_username)
                return sub, mb

            pairs = await _map_limited(sem, subs, fetch_mb)
            for item in pairs:
                if isinstance(item, Exception):
                    logger.warning("sync fetch failed: %s", item)
                    continue
                sub, mb = item
                try:
                    await sync.apply_marzban_user(session, sub, mb)
                except Exception as e:
                    logger.warning("sync failed %s: %s", sub.marzban_username, e)
            await session.commit()

    async def sync_limiters() -> None:
        s = get_settings()
        sync = get_sync_service()
        sem = asyncio.Semaphore(s.scheduler_max_concurrency)
        failed = 0
        async with async_session_factory() as session:
            subs = (
                await session.scalars(
                    select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE)
                )
            ).all()

            async def sync_one(sub: Subscription):
                return sub, await sync.sync_limiters_for_subscription(sub)

            results = await _map_limited(sem, subs, sync_one)
            for item in results:
                if isinstance(item, Exception):
                    failed += 1
                    logger.warning("sync_limiters item failed: %s", item)
                    continue
                _, ok = item
                if not ok:
                    failed += 1
            await session.commit()
        if failed:
            logger.warning("sync_limiters: %s failures", failed)

    async def sync_trials() -> None:
        s = get_settings()
        sync = get_sync_service()
        sem = asyncio.Semaphore(s.scheduler_max_concurrency)
        async with async_session_factory() as session:
            subs = (
                await session.scalars(
                    select(Subscription).where(
                        Subscription.is_trial.is_(True),
                        Subscription.status.in_(
                            [SubscriptionStatus.ACTIVE, SubscriptionStatus.LIMITED]
                        ),
                    )
                )
            ).all()

            async def fetch_mb(sub: Subscription):
                mb = await sync._marzban.get_user(sub.marzban_username)
                return sub, mb

            pairs = await _map_limited(sem, subs, fetch_mb)
            for item in pairs:
                if isinstance(item, Exception):
                    logger.warning("trial sync fetch failed: %s", item)
                    continue
                sub, mb = item
                try:
                    await sync.apply_marzban_user(session, sub, mb)
                except Exception as e:
                    logger.warning("trial sync failed %s: %s", sub.marzban_username, e)
            await session.commit()

    async def stuck_orders() -> None:
        threshold = datetime.now(UTC) - timedelta(minutes=10)
        async with async_session_factory() as session:
            stuck = (
                await session.scalars(
                    select(Order).where(
                        Order.status == OrderStatus.PROVISIONING,
                        Order.updated_at < threshold,
                    )
                )
            ).all()
            if stuck:
                hub = NotificationHub(bot, session)
                await hub.alert(
                    "stuck_orders",
                    f"⚠️ {len(stuck)} سفارش در provisioning گیر کرده است.",
                    severity="warning",
                    context="global",
                    to_admins=True,
                    to_ops=True,
                    throttle=True,
                    buttons=[("📋 سفارش‌ها", "admin:orders"), ("📥 صندوق", "admin:inbox")],
                )
                await session.commit()

    async def limiter_health() -> None:
        m_ok, _, _ = await get_marzban().health_check()
        i_ok, _, _ = await get_ip_limiter().health_check()
        if not (m_ok and i_ok):
            async with async_session_factory() as session:
                hub = NotificationHub(bot, session)
                await hub.alert(
                    "limiter_health",
                    f"⚠️ سلامت سرویس: Marzban={m_ok} IP={i_ok}",
                    severity="error",
                    context="global",
                    to_admins=True,
                    to_ops=True,
                    throttle=True,
                    buttons=[("🔍 دیباگ", "admin:debug"), ("📥 صندوق", "admin:inbox")],
                )
                await session.commit()

    async def expire_notifications() -> None:
        now = datetime.now(UTC)
        for days in (3, 1):
            target_start = now + timedelta(days=days - 1)
            target_end = now + timedelta(days=days)
            async with async_session_factory() as session:
                subs = (
                    await session.scalars(
                        select(Subscription)
                        .options(selectinload(Subscription.user))
                        .where(
                            Subscription.status == SubscriptionStatus.ACTIVE,
                            Subscription.expires_at >= target_start,
                            Subscription.expires_at < target_end,
                        )
                    )
                ).all()
                for sub in subs:
                    user = sub.user
                    if not user:
                        continue
                    try:
                        kb = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="🔄 تمدید الان",
                                        callback_data=f"renew:start:{sub.id}",
                                    )
                                ]
                            ]
                        )
                        await bot.send_message(
                            user.telegram_id,
                            f"⏰ سرویس {sub.label or sub.marzban_username} تا {days} روز دیگر منقضی می‌شود.",
                            reply_markup=kb,
                        )
                    except Exception:
                        pass

    async def daily_digest() -> None:
        async with async_session_factory() as session:
            enabled, _, _ = await get_digest_schedule(session)
            if not enabled:
                return
            text = await build_daily_digest(session)
        kb = _alert_kb(
            [
                ("📥 صندوق", "admin:inbox"),
                ("👥 کاربران", "admin:hub:users"),
                ("📢 پیام", "admin:messaging"),
            ]
        )
        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(admin_id, text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass

    async def traffic_anomaly_guard() -> None:
        s = get_settings()
        service = TrafficAnomalyService(s, get_marzban())
        async with async_session_factory() as session:
            normal, watch, disabled = await service.run_guard(session, bot)
            logger.info(
                "traffic_anomaly_guard done normal=%s watch=%s disabled=%s",
                normal,
                watch,
                disabled,
            )
            await session.commit()

    async def traffic_anomaly_cleanup() -> None:
        s = get_settings()
        service = TrafficAnomalyService(s, get_marzban())
        async with async_session_factory() as session:
            deleted_snapshots, deleted_events = await service.cleanup_old_data(session, days=30)
            if deleted_snapshots or deleted_events:
                logger.info(
                    "traffic_anomaly_cleanup deleted snapshots=%s events=%s",
                    deleted_snapshots,
                    deleted_events,
                )
            await session.commit()

    async def sync_subscriptions_job() -> None:
        await _safe_job("sync_subscriptions", sync_subscriptions)

    async def sync_limiters_job() -> None:
        await _safe_job("sync_limiters", sync_limiters)

    async def sync_trials_job() -> None:
        await _safe_job("sync_trials", sync_trials)

    async def traffic_anomaly_guard_job() -> None:
        await _safe_job("traffic_anomaly_guard", traffic_anomaly_guard)

    scheduler.add_job(sync_subscriptions_job, "interval", minutes=15, id="sync_subscriptions")
    scheduler.add_job(sync_limiters_job, "interval", minutes=30, id="sync_limiters")
    scheduler.add_job(
        sync_trials_job,
        "interval",
        minutes=settings.trial_sync_interval_minutes,
        id="sync_trials",
    )
    scheduler.add_job(stuck_orders, "interval", minutes=5, id="stuck_orders")
    scheduler.add_job(limiter_health, "interval", minutes=1, id="limiter_health")
    scheduler.add_job(expire_notifications, "cron", hour=9, minute=0, id="expire_notifications")
    scheduler.add_job(
        traffic_anomaly_guard_job,
        "interval",
        minutes=max(5, settings.traffic_anomaly_interval_minutes),
        id="traffic_anomaly_guard",
    )
    scheduler.add_job(
        traffic_anomaly_cleanup,
        "cron",
        hour=3,
        minute=15,
        id="traffic_anomaly_cleanup",
    )

    job_registry.set_scheduler(scheduler)
    job_registry.set_digest_callable(daily_digest)
    enabled, hour, minute = True, settings.ops_digest_hour, settings.ops_digest_minute
    job_registry.reschedule_digest(hour, minute, enabled=enabled)

    return scheduler
