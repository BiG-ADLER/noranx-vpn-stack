from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.admin_help_catalog import SECTION_ORDER, SECTIONS


def help_hub_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    pair: list[InlineKeyboardButton] = []
    for sid in SECTION_ORDER:
        sec = SECTIONS[sid]
        btn = InlineKeyboardButton(
            text=f"{sec.emoji} {sec.title.split()[0]}",
            callback_data=f"admin:help:section:{sid}",
        )
        pair.append(btn)
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append(
        [InlineKeyboardButton(text="📋 همه دستورات", callback_data="admin:help:commands:0")]
    )
    rows.append(
        [
            InlineKeyboardButton(text="« پنل ادمین", callback_data="menu:admin"),
            InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="admin:help"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def help_section_kb(section_id: str) -> InlineKeyboardMarkup:
    sec = SECTIONS[section_id]
    rows: list[list[InlineKeyboardButton]] = []
    for action in sec.actions:
        rows.append(
            [InlineKeyboardButton(text=action.label, callback_data=action.callback_data)]
        )
    rows.append(
        [
            InlineKeyboardButton(text="« راهنما", callback_data="admin:help"),
            InlineKeyboardButton(text="📋 دستورات", callback_data="admin:help:commands:0"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def help_commands_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀ قبلی", callback_data=f"admin:help:commands:{page - 1}")
        )
    nav.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data=f"admin:help:commands:{page}",
        )
    )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(text="بعدی ▶", callback_data=f"admin:help:commands:{page + 1}")
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            nav,
            [
                InlineKeyboardButton(text="« راهنما", callback_data="admin:help"),
                InlineKeyboardButton(text="« پنل ادمین", callback_data="menu:admin"),
            ],
        ]
    )
