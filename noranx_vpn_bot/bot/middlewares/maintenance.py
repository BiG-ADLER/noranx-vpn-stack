from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.services import bot_content


class MaintenanceMiddleware(BaseMiddleware):
    PURCHASE_PREFIXES = ("shop:", "pay:", "trial:", "renew:", "wallet:", "menu:shop", "menu:trial", "menu:wallet")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        if session is not None:
            if not await bot_content.is_maintenance_mode(session):
                return await handler(event, data)
            msg = await bot_content.get_maintenance_message(session)
        else:
            from bot.db.session import async_session_factory

            async with async_session_factory() as session:
                if not await bot_content.is_maintenance_mode(session):
                    return await handler(event, data)
                msg = await bot_content.get_maintenance_message(session)
        if isinstance(event, CallbackQuery) and event.data:
            if any(event.data.startswith(p) for p in self.PURCHASE_PREFIXES):
                await event.answer(msg, show_alert=True)
                return None
        if isinstance(event, Message) and event.text and event.text.startswith("/"):
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data and any(
            event.data.startswith(p) for p in self.PURCHASE_PREFIXES
        ):
            return None
        return await handler(event, data)
