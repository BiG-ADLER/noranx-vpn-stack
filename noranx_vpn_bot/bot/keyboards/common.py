from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def cancel_fsm_kb(callback: str = "fsm:cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ لغو", callback_data=callback)]]
    )


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="« منوی اصلی", callback_data="menu:main")]]
    )


def back_to_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="« پنل ادمین", callback_data="menu:admin")]]
    )
