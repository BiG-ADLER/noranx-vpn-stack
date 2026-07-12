"""Runtime bot copy from settings with hardcoded fallbacks."""

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Setting

DEFAULTS = {
    "bot_welcome_text": "به NoranX VPN خوش آمدید!\n\nاز منوی زیر سرویس خود را مدیریت کنید.",
    "bot_welcome_new_text": (
        "به NoranX VPN خوش آمدید!\n\nبرای شروع یکی از گزینه‌های زیر را انتخاب کنید:"
    ),
    "bot_shop_header": "🛒 انتخاب پلن (۱ ماهه — قیمت به تومان)",
    "bot_admin_panel_title": "پنل مدیریت:\n\n📚 برای فهرست دستورات و وضعیت سریع: /help",
    "maintenance_mode": "false",
    "maintenance_message": "🔧 ربات در حال تعمیر است. لطفاً بعداً مراجعه کنید.",
    "ops_digest_enabled": "true",
    "ops_digest_hour": "9",
    "ops_digest_minute": "0",
    "alert_throttle_minutes": "15",
    "alert_new_user_ops": "false",
    "referral_wallet_reward_toman": "10000",
}


async def get_setting(session: AsyncSession, key: str) -> str:
    row = await session.get(Setting, key)
    if row and row.value:
        return row.value
    return DEFAULTS.get(key, "")


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(Setting, key)
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))


async def get_welcome_text(session: AsyncSession, *, is_new: bool = False) -> str:
    key = "bot_welcome_new_text" if is_new else "bot_welcome_text"
    return await get_setting(session, key)


async def get_shop_header(session: AsyncSession) -> str:
    return await get_setting(session, "bot_shop_header")


async def get_admin_panel_title(session: AsyncSession) -> str:
    return await get_setting(session, "bot_admin_panel_title")


async def is_maintenance_mode(session: AsyncSession) -> bool:
    return (await get_setting(session, "maintenance_mode")).lower() in ("1", "true", "yes", "on")


async def get_maintenance_message(session: AsyncSession) -> str:
    return await get_setting(session, "maintenance_message")


async def get_referral_wallet_reward_toman(session: AsyncSession) -> int:
    from bot.config import get_settings

    raw = await get_setting(session, "referral_wallet_reward_toman")
    if raw.strip().isdigit():
        return int(raw.strip())
    return get_settings().referral_wallet_reward_toman
