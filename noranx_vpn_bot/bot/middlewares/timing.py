import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from bot.utils.logging import get_logger

logger = get_logger("handler_timing")


def _update_type(event: TelegramObject) -> str:
    if isinstance(event, Update):
        for name in (
            "message",
            "callback_query",
            "inline_query",
            "edited_message",
            "channel_post",
            "my_chat_member",
        ):
            if getattr(event, name, None):
                return name
        return "update"
    if isinstance(event, Message):
        return "message"
    if isinstance(event, CallbackQuery):
        return "callback_query"
    return type(event).__name__


def _actor_id(event: TelegramObject) -> int | None:
    if isinstance(event, Update):
        if event.message and event.message.from_user:
            return event.message.from_user.id
        if event.callback_query and event.callback_query.from_user:
            return event.callback_query.from_user.id
        return None
    if isinstance(event, Message) and event.from_user:
        return event.from_user.id
    if isinstance(event, CallbackQuery) and event.from_user:
        return event.from_user.id
    return None


class TimingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        start = time.perf_counter()
        try:
            return await handler(event, data)
        finally:
            ms = int((time.perf_counter() - start) * 1000)
            logger.info(
                "handler_timing update_type=%s actor_id=%s ms=%s",
                _update_type(event),
                _actor_id(event),
                ms,
            )
