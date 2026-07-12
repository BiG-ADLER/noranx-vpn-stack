from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.admin_ops import OpsSnapshot, badge


def inbox_kb(snapshot: OpsSnapshot) -> InlineKeyboardMarkup:
    c2c_total = snapshot.c2c_review + snapshot.c2c_waiting
    orders_total = snapshot.stuck_orders + snapshot.failed_orders
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"💳 C2C{badge(c2c_total)}",
                    callback_data="admin:payments",
                ),
                InlineKeyboardButton(
                    text=f"🎫 تیکت‌ها{badge(snapshot.open_tickets)}",
                    callback_data="admin:tickets:open",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"📋 سفارش‌ها{badge(orders_total)}",
                    callback_data="admin:orders",
                ),
                InlineKeyboardButton(
                    text="🔍 دیباگ",
                    callback_data="admin:debug",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔒 همگام limiter",
                    callback_data="admin:ops:limiter_sync",
                ),
                InlineKeyboardButton(text="📚 راهنما", callback_data="admin:help"),
            ],
            [
                InlineKeyboardButton(text="« پنل ادمین", callback_data="menu:admin"),
                InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="admin:inbox"),
            ],
        ]
    )


def debug_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔒 همگام limiter",
                    callback_data="admin:ops:limiter_sync",
                ),
                InlineKeyboardButton(text="💳 C2C", callback_data="admin:payments"),
            ],
            [
                InlineKeyboardButton(text="📋 سفارش‌ها", callback_data="admin:orders"),
                InlineKeyboardButton(text="📥 صندوق", callback_data="admin:inbox"),
            ],
            [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="admin:debug")],
            [InlineKeyboardButton(text="« پنل ادمین", callback_data="menu:admin")],
        ]
    )
