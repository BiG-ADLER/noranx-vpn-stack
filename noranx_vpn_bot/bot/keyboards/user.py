from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import get_settings
from bot.db.models import Plan, RechargePackage, Subscription
from bot.services.payment.c2c_utils import c2c_available


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🛒 خرید سرویس", callback_data="menu:shop"),
            InlineKeyboardButton(text="📦 سرویس‌های من", callback_data="menu:accounts"),
        ],
        [
            InlineKeyboardButton(text="💰 کیف پول", callback_data="menu:wallet"),
            InlineKeyboardButton(text="🎁 تست رایگان", callback_data="menu:trial"),
        ],
        [
            InlineKeyboardButton(text="👥 دعوت دوستان", callback_data="menu:referral"),
            InlineKeyboardButton(text="🎫 پشتیبانی", callback_data="menu:support"),
        ],
        [
            InlineKeyboardButton(text="📖 راهنما", callback_data="menu:guide"),
        ],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="⚙️ پنل ادمین", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_kb(plans: list[Plan]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{p.name_fa} — {p.price_toman:,} تومان",
                callback_data=f"shop:plan:{p.slug}",
            )
        ]
        for p in plans
    ]
    rows.append([InlineKeyboardButton(text="« بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quantity_kb(plan_slug: str, max_qty: int) -> InlineKeyboardMarkup:
    rows = []
    for i in range(1, min(max_qty, 5) + 1):
        rows.append(
            [
                InlineKeyboardButton(
                    text=str(i), callback_data=f"shop:qty:{plan_slug}:{i}"
                )
            ]
        )
    if max_qty > 5:
        rows.append(
            [
                InlineKeyboardButton(text="۵+", callback_data=f"shop:qty_more:{plan_slug}")
            ]
        )
    rows.append([InlineKeyboardButton(text="« بازگشت", callback_data="menu:shop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def username_choice_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔤 نام پیش‌فرض",
                    callback_data=f"shop:uname:default:{order_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ نام دلخواه",
                    callback_data=f"shop:uname:custom:{order_id}",
                ),
            ],
            [InlineKeyboardButton(text="« لغو", callback_data="menu:shop")],
        ]
    )


def checkout_kb(order_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="💰 پرداخت از کیف پول",
                callback_data=f"pay:wallet:{order_id}",
            )
        ],
    ]
    if c2c_available(get_settings()):
        rows.append(
            [
                InlineKeyboardButton(
                    text="💳 کارت به کارت",
                    callback_data=f"pay:c2c:{order_id}",
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🏷 کد تخفیف",
                    callback_data=f"shop:discount:{order_id}",
                )
            ],
            [
                InlineKeyboardButton(text="💰 شارژ کیف پول", callback_data="wallet:recharge"),
            ],
            [InlineKeyboardButton(text="« لغو", callback_data="menu:shop")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


CHECKOUT_CRYPTO_HINT = (
    "برای پرداخت با ارز دیجیتال، ابتدا کیف پول را شارژ کنید (حداقل ۵ دلار)، "
    "سپس از موجودی خرید کنید."
)


def subscriptions_kb(subs: list[Subscription]) -> InlineKeyboardMarkup:
    rows = []
    for s in subs:
        label = s.label or s.marzban_username
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{'🟢' if s.status.value == 'active' else '🔴'} {label}",
                    callback_data=f"acc:view:{s.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="🛒 خرید جدید", callback_data="menu:shop"),
            InlineKeyboardButton(text="« منو", callback_data="menu:main"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def account_detail_kb(sub_id: int, plan_id: int | None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🔄 بروزرسانی", callback_data=f"acc:refresh:{sub_id}"),
            InlineKeyboardButton(text="📷 QR", callback_data=f"acc:qr:{sub_id}"),
        ],
        [
            InlineKeyboardButton(text="📊 مصرف", callback_data=f"acc:usage:{sub_id}"),
        ],
    ]
    if plan_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 تمدید", callback_data=f"renew:start:{sub_id}"
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="📖 راهنما", callback_data="menu:guide"),
            InlineKeyboardButton(text="« بازگشت", callback_data="menu:accounts"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wallet_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ شارژ کیف پول", callback_data="wallet:recharge")],
            [InlineKeyboardButton(text="« منو", callback_data="menu:main")],
        ]
    )


def recharge_menu_kb() -> InlineKeyboardMarkup:
    from bot.services.payment.c2c_utils import c2c_available
    from bot.services.payment.nowpayments import NowPaymentsService

    settings = get_settings()
    rows = []
    if NowPaymentsService(settings).enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="₿ شارژ با کریپتو",
                    callback_data="wallet:crypto:custom",
                )
            ]
        )
    if c2c_available(settings):
        rows.append(
            [
                InlineKeyboardButton(
                    text="💳 کارت به کارت",
                    callback_data="wallet:c2c:packages",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="« بازگشت", callback_data="menu:wallet")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def recharge_packages_kb(packages: list[RechargePackage]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{p.amount_toman:,} تومان",
                callback_data=f"wallet:pkg:{p.id}",
            )
        ]
        for p in packages
    ]
    rows.append([InlineKeyboardButton(text="« بازگشت", callback_data="wallet:recharge")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def crypto_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تأیید", callback_data="wallet:crypto:confirm"),
                InlineKeyboardButton(text="❌ لغو", callback_data="wallet:recharge"),
            ],
        ]
    )


def onboarding_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎁 تست رایگان", callback_data="menu:trial"),
                InlineKeyboardButton(text="📖 راهنما", callback_data="menu:guide"),
            ],
            [InlineKeyboardButton(text="🛒 خرید سرویس", callback_data="menu:shop")],
        ]
    )


def back_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="« منوی اصلی", callback_data="menu:main")]]
    )
