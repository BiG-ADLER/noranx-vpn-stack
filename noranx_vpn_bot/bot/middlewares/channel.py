from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.services import channel_gate as gate
from bot.utils.logging import get_logger
from bot.utils.telegram import safe_callback_answer

logger = get_logger("channel_gate")

_gate_trace_admins: set[int] = set()


def set_gate_trace(admin_id: int, enabled: bool) -> None:
    if enabled:
        _gate_trace_admins.add(admin_id)
    else:
        _gate_trace_admins.discard(admin_id)


def is_gate_trace(admin_id: int) -> bool:
    return admin_id in _gate_trace_admins


class StrictChannelMiddleware(BaseMiddleware):
    """Blocks all bot usage until user joins required channel (admins exempt)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = gate.extract_user_id(event)
        if user_id is None:
            return await handler(event, data)

        if gate.is_exempt(user_id):
            if is_gate_trace(user_id):
                logger.info("channel_gate decision=allowed user_id=%s exempt=1", user_id)
            return await handler(event, data)

        if gate.is_recheck_callback(event) or gate.is_start_command(event):
            return await handler(event, data)

        bot = data["bot"]
        if await gate.is_channel_member(bot, user_id):
            if is_gate_trace(user_id):
                update_type = "callback_query" if isinstance(event, CallbackQuery) else "message"
                data_hint = event.data if isinstance(event, CallbackQuery) else (event.text or "")[:40]
                logger.info(
                    "channel_gate decision=allowed user_id=%s member=1 update_type=%s data=%s",
                    user_id,
                    update_type,
                    data_hint,
                )
            return await handler(event, data)

        update_type = "callback_query" if isinstance(event, CallbackQuery) else "message"
        data_hint = ""
        if isinstance(event, CallbackQuery):
            data_hint = event.data or ""
        elif isinstance(event, Message):
            data_hint = (event.text or "")[:40]

        logger.info(
            "channel_gate decision=blocked user_id=%s update_type=%s data=%s",
            user_id,
            update_type,
            data_hint,
        )

        if isinstance(event, CallbackQuery):
            if event.message:
                await gate.send_gate_screen(bot, event.message.chat.id, edit_message=event.message)
            await safe_callback_answer(event, "ابتدا در کانال عضو شوید.", show_alert=True)
            return None

        if isinstance(event, Message):
            await gate.send_gate_screen(bot, event.chat.id)
            return None

        return None


# Backward-compatible alias for imports
ChannelCheckMiddleware = StrictChannelMiddleware
