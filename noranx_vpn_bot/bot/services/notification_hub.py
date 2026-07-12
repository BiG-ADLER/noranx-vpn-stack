"""Unified alert routing with deduplication."""

from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import NotificationLog, Setting
from bot.services import bot_content
from bot.utils.logging import get_logger

logger = get_logger("notify")


class NotificationHub:
    def __init__(self, bot: Bot, session: AsyncSession):
        self.bot = bot
        self.session = session
        self.settings = get_settings()

    async def _throttle_minutes(self) -> int:
        raw = await bot_content.get_setting(self.session, "alert_throttle_minutes")
        try:
            return max(1, int(raw))
        except ValueError:
            return 15

    async def _ops_channel_id(self) -> int:
        raw = await bot_content.get_setting(self.session, "ops_channel_id")
        if raw and raw.lstrip("-").isdigit():
            return int(raw)
        return self.settings.ops_channel_id

    async def _announcement_channel_id(self) -> int:
        raw = await bot_content.get_setting(self.session, "announcement_channel_id")
        if raw and raw.lstrip("-").isdigit():
            return int(raw)
        return self.settings.announcement_channel_id

    async def _should_send(self, dedup_key: str) -> bool:
        since = datetime.now(UTC) - timedelta(minutes=await self._throttle_minutes())
        recent = await self.session.scalar(
            select(NotificationLog.id)
            .where(NotificationLog.dedup_key == dedup_key, NotificationLog.created_at >= since)
            .limit(1)
        )
        return recent is None

    async def _log(self, dedup_key: str, severity: str, channel: str, body: str) -> None:
        self.session.add(
            NotificationLog(
                dedup_key=dedup_key,
                severity=severity,
                channel=channel,
                body=body[:2000],
            )
        )

    async def notify_admins(
        self,
        text: str,
        *,
        dedup_key: str | None = None,
        severity: str = "info",
        reply_markup: InlineKeyboardMarkup | None = None,
        throttle: bool = False,
    ) -> None:
        if throttle and dedup_key and not await self._should_send(dedup_key):
            return
        for admin_id in self.settings.admin_ids:
            try:
                await self.bot.send_message(
                    admin_id, text, reply_markup=reply_markup, parse_mode="HTML"
                )
            except Exception as e:
                logger.warning("notify admin %s failed: %s", admin_id, e)
        if dedup_key:
            await self._log(dedup_key, severity, "admins", text)

    async def notify_ops_channel(
        self,
        text: str,
        *,
        dedup_key: str | None = None,
        severity: str = "info",
        throttle: bool = False,
    ) -> None:
        channel_id = await self._ops_channel_id()
        if not channel_id:
            return
        if throttle and dedup_key and not await self._should_send(dedup_key):
            return
        try:
            await self.bot.send_message(channel_id, text, parse_mode="HTML")
            if dedup_key:
                await self._log(dedup_key, severity, "ops_channel", text)
        except Exception as e:
            logger.warning("notify ops channel failed: %s", e)

    async def notify_announcement_channel(self, text: str, *, photo_file_id: str | None = None) -> bool:
        channel_id = await self._announcement_channel_id()
        if not channel_id:
            return False
        try:
            if photo_file_id:
                await self.bot.send_photo(channel_id, photo_file_id, caption=text, parse_mode="HTML")
            else:
                await self.bot.send_message(channel_id, text, parse_mode="HTML")
            return True
        except Exception as e:
            logger.warning("announcement channel post failed: %s", e)
            return False

    async def alert(
        self,
        event_type: str,
        text: str,
        *,
        severity: str = "warning",
        context: str = "",
        to_admins: bool = True,
        to_ops: bool = False,
        throttle: bool = True,
        buttons: list[tuple[str, str]] | None = None,
    ) -> None:
        dedup_key = f"{event_type}:{context}" if context else event_type
        kb = None
        if buttons:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=l, callback_data=c)] for l, c in buttons
                ]
            )
        if to_admins:
            await self.notify_admins(
                text, dedup_key=dedup_key, severity=severity, reply_markup=kb, throttle=throttle
            )
        if to_ops:
            await self.notify_ops_channel(text, dedup_key=dedup_key, severity=severity, throttle=throttle)

    async def notify_new_user(self, telegram_id: int, username: str | None) -> None:
        flag = await bot_content.get_setting(self.session, "alert_new_user_ops")
        if flag.lower() not in ("1", "true", "yes", "on"):
            return
        name = f"@{username}" if username else str(telegram_id)
        await self.notify_ops_channel(
            f"👤 کاربر جدید: {name} (<code>{telegram_id}</code>)",
            dedup_key=f"new_user:{telegram_id}",
            severity="info",
            throttle=False,
        )

    async def notify_purchase(self, user_tg_id: int, amount: int, detail: str) -> None:
        text = f"💰 خرید جدید\nکاربر: <code>{user_tg_id}</code>\nمبلغ: {amount:,} تومان\n{detail}"
        await self.alert("purchase", text, severity="info", to_admins=True, to_ops=True, throttle=False)
