from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def channel_gate_kb(channel_link: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if channel_link:
        rows.append(
            [InlineKeyboardButton(text="📢 عضویت در کانال", url=channel_link)]
        )
    rows.append(
        [InlineKeyboardButton(text="✅ بررسی عضویت", callback_data="channel:recheck")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
