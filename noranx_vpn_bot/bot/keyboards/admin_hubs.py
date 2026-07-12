from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Admin UX: hub child screens use parent-hub back buttons; infra/commerce/settings hubs are canonical entry points.

from bot.services.admin_ops import OpsSnapshot, badge


def admin_root_kb(snapshot: OpsSnapshot | None = None) -> InlineKeyboardMarkup:
    s = snapshot
    inbox_n = s.total_actionable if s else 0
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📥 صندوق عملیات{badge(inbox_n)}",
                    callback_data="admin:inbox",
                ),
            ],
            [
                InlineKeyboardButton(text="👥 کاربران و پیام", callback_data="admin:hub:users"),
                InlineKeyboardButton(text="🛒 فروش و پلن‌ها", callback_data="admin:hub:commerce"),
            ],
            [
                InlineKeyboardButton(text="📖 راهنما و محتوا", callback_data="admin:hub:content"),
                InlineKeyboardButton(text="🖥 زیرساخت", callback_data="admin:hub:infra"),
            ],
            [
                InlineKeyboardButton(text="⚙️ تنظیمات و گزارش", callback_data="admin:hub:settings"),
                InlineKeyboardButton(text="📚 راهنمای ادمین", callback_data="admin:help"),
            ],
            [InlineKeyboardButton(text="« بازگشت", callback_data="menu:main")],
        ]
    )


def users_hub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 جستجو", callback_data="admin:users:search"),
                InlineKeyboardButton(text="📊 همه کاربران", callback_data="admin:dir:all_started:0"),
            ],
            [
                InlineKeyboardButton(text="❌ بدون خرید", callback_data="admin:dir:never_purchased:0"),
                InlineKeyboardButton(text="✅ اشتراک فعال", callback_data="admin:dir:active_subscribers:0"),
            ],
            [
                InlineKeyboardButton(text="⏰ منقضی", callback_data="admin:dir:expired:0"),
                InlineKeyboardButton(text="🎁 فقط تست", callback_data="admin:dir:trial_only:0"),
            ],
            [
                InlineKeyboardButton(text="🛒 خرید کرده", callback_data="admin:dir:has_purchased:0"),
                InlineKeyboardButton(text="🚫 مسدود", callback_data="admin:dir:banned:0"),
            ],
            [
                InlineKeyboardButton(text="📢 پیام‌رسانی", callback_data="admin:messaging"),
            ],
            [InlineKeyboardButton(text="« پنل ادمین", callback_data="menu:admin")],
        ]
    )


def commerce_hub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 پلن‌های VPN", callback_data="admin:plans")],
            [InlineKeyboardButton(text="💳 بسته‌های شارژ", callback_data="admin:packages")],
            [InlineKeyboardButton(text="🏷 تخفیف‌ها", callback_data="admin:discounts")],
            [InlineKeyboardButton(text="✏️ متن‌های ربات", callback_data="admin:commerce:copy")],
            [InlineKeyboardButton(text="« پنل ادمین", callback_data="menu:admin")],
        ]
    )


def content_hub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📖 راهنمای اتصال (مدیریت)", callback_data="admin:guides")],
            [InlineKeyboardButton(text="« پنل ادمین", callback_data="menu:admin")],
        ]
    )


def infra_hub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🖥 Marzban", callback_data="admin:marzban:list:0"),
                InlineKeyboardButton(text="🔍 دیباگ", callback_data="admin:debug"),
            ],
            [
                InlineKeyboardButton(text="📋 سفارش‌ها", callback_data="admin:orders"),
                InlineKeyboardButton(text="💳 C2C", callback_data="admin:payments"),
            ],
            [InlineKeyboardButton(text="🎫 تیکت‌ها", callback_data="admin:tickets")],
            [InlineKeyboardButton(text="« پنل ادمین", callback_data="menu:admin")],
        ]
    )


def settings_hub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 گزارش روزانه", callback_data="admin:ops:report")],
            [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="admin:settings")],
            [InlineKeyboardButton(text="💰 کیف پول", callback_data="admin:wallet")],
            [InlineKeyboardButton(text="« پنل ادمین", callback_data="menu:admin")],
        ]
    )
