from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def marzban_list_kb(page: int, total: int, limit: int = 10) -> InlineKeyboardMarkup:
    rows = []
    max_page = max(0, (total - 1) // limit) if total else 0
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀", callback_data=f"admin:marzban:list:{page - 1}")
        )
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{max_page + 1}", callback_data=f"admin:marzban:list:{page}"))
    if page < max_page:
        nav.append(
            InlineKeyboardButton(text="▶", callback_data=f"admin:marzban:list:{page + 1}")
        )
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(text="🔍 Drift", callback_data="admin:marzban:drift"),
            InlineKeyboardButton(text="« زیرساخت", callback_data="admin:hub:infra"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def marzban_user_kb(username: str) -> InlineKeyboardMarkup:
    u = username
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ فعال", callback_data=f"admin:marzban:enable:{u}"),
                InlineKeyboardButton(text="⛔ غیرفعال", callback_data=f"admin:marzban:disable:{u}"),
            ],
            [
                InlineKeyboardButton(text="📅 +روز", callback_data=f"admin:marzban:extend:{u}"),
                InlineKeyboardButton(text="🔄 ریست ترافیک", callback_data=f"admin:marzban:reset:{u}"),
            ],
            [
                InlineKeyboardButton(text="🔗 Sync DB", callback_data=f"admin:marzban:sync:{u}"),
                InlineKeyboardButton(text="📥 Import", callback_data=f"admin:marzban:import:{u}"),
            ],
            [
                InlineKeyboardButton(text="🗑 حذف", callback_data=f"admin:marzban:delete:{u}"),
            ],
            [InlineKeyboardButton(text="« لیست", callback_data="admin:marzban:list:0")],
        ]
    )


def marzban_user_row_kb(username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=username[:28],
                    callback_data=f"admin:marzban:view:{username}",
                )
            ]
        ]
    )
