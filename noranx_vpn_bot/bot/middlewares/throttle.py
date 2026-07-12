import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import get_settings
from bot.utils.telegram import safe_callback_answer

_settings = get_settings()
_buckets: dict[int, list[float]] = {}
_LIMIT = 20
_WINDOW = 60.0


class ThrottleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
        if user_id and user_id not in _settings.admin_ids:
            now = time.time()
            hits = _buckets.get(user_id, [])
            hits = [t for t in hits if now - t < _WINDOW]
            if len(hits) >= _LIMIT:
                if isinstance(event, CallbackQuery):
                    await safe_callback_answer(event, "لطفاً کمی صبر کنید.", show_alert=True)
                return None
            hits.append(now)
            _buckets[user_id] = hits
        return await handler(event, data)
