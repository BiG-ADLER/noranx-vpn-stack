from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

ADMIN_REPLY_LABELS = {
    "📥 صندوق": "admin:inbox",
    "💳 C2C": "admin:payments",
    "🎫 تیکت": "admin:tickets",
    "🔍 دیباگ": "admin:debug",
    "📚 راهنما": "admin:help",
}


def admin_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 صندوق"), KeyboardButton(text="💳 C2C")],
            [KeyboardButton(text="🎫 تیکت"), KeyboardButton(text="🔍 دیباگ")],
            [KeyboardButton(text="📚 راهنما")],
        ],
        resize_keyboard=True,
    )


def remove_reply_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
