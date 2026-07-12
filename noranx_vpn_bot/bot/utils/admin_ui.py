from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import get_settings
from bot.utils.telegram import safe_callback_answer


def is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


async def admin_guard(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True
    await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
    return False


def hub_back_kb(parent_callback: str, label: str = "« بازگشت") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=parent_callback)]]
    )


async def edit_screen(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    parse_mode: str | None = "HTML",
) -> None:
    await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    await safe_callback_answer(callback)
