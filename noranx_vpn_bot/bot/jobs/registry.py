"""APScheduler job registry with Tehran timezone support."""

from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.utils.logging import get_logger

logger = get_logger("scheduler_registry")

TEHRAN = ZoneInfo("Asia/Tehran")

_scheduler: AsyncIOScheduler | None = None
_digest_callable = None


def set_scheduler(scheduler: AsyncIOScheduler) -> None:
    global _scheduler
    _scheduler = scheduler


def set_digest_callable(fn) -> None:
    global _digest_callable
    _digest_callable = fn


def reschedule_digest(hour: int, minute: int, *, enabled: bool = True) -> None:
    if not _scheduler or not _digest_callable:
        logger.warning("scheduler not ready for digest reschedule")
        return
    try:
        _scheduler.remove_job("daily_digest")
    except Exception:
        pass
    if not enabled:
        logger.info("daily_digest disabled")
        return
    _scheduler.add_job(
        _digest_callable,
        "cron",
        hour=hour,
        minute=minute,
        timezone=TEHRAN,
        id="daily_digest",
        replace_existing=True,
    )
    logger.info("daily_digest rescheduled to %02d:%02d Tehran", hour, minute)


async def send_digest_now(bot: Bot) -> None:
    from bot.db.session import async_session_factory
    from bot.services.reports import build_daily_digest
    from bot.config import get_settings
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    settings = get_settings()
    async with async_session_factory() as session:
        text = await build_daily_digest(session)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📥 صندوق", callback_data="admin:inbox"),
                InlineKeyboardButton(text="👥 کاربران", callback_data="admin:hub:users"),
            ],
            [InlineKeyboardButton(text="📢 پیام‌رسانی", callback_data="admin:messaging")],
        ]
    )
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
