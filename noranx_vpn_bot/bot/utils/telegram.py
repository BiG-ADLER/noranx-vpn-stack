from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery


async def safe_callback_answer(callback: CallbackQuery, *args, **kwargs) -> None:
    """Answer callback; ignore expired queries after bot restart or slow handlers."""
    try:
        await callback.answer(*args, **kwargs)
    except TelegramBadRequest as e:
        msg = (e.message or "").lower()
        if "query is too old" in msg or "query id is invalid" in msg:
            return
        raise
