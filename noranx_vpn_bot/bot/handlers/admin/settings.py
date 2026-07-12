from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import Setting
from bot.keyboards.common import cancel_fsm_kb
from bot.services import bot_content
from bot.services.reports import get_digest_schedule
from bot.states import AdminStates
from bot.utils.admin_ui import admin_guard
from bot.utils.telegram import safe_callback_answer

router = Router()

SETTING_CATEGORIES = {
    "channels": [
        ("ops_channel_id", "کانال عملیات"),
        ("announcement_channel_id", "کانال اطلاع‌رسانی"),
    ],
    "alerts": [
        ("alert_throttle_minutes", "فاصله هشدار (دقیقه)"),
        ("alert_new_user_ops", "هشدار کاربر جدید"),
    ],
    "digest": [
        ("digest_enabled", "گزارش روزانه"),
        ("digest_hour", "ساعت گزارش"),
        ("digest_minute", "دقیقه گزارش"),
    ],
    "runtime": [
        ("maintenance_mode", "حالت تعمیر"),
    ],
    "referral": [
        ("referral_wallet_reward_toman", "پاداش دعوت (تومان)"),
    ],
}


def _settings_hub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 کانال‌ها", callback_data="admin:settings:cat:channels")],
            [InlineKeyboardButton(text="🔔 هشدارها", callback_data="admin:settings:cat:alerts")],
            [InlineKeyboardButton(text="📊 گزارش روزانه", callback_data="admin:settings:cat:digest")],
            [InlineKeyboardButton(text="⚙️ زمان‌بندی", callback_data="admin:settings:cat:runtime")],
            [InlineKeyboardButton(text="👥 دعوت", callback_data="admin:settings:cat:referral")],
            [InlineKeyboardButton(text="« تنظیمات و گزارش", callback_data="admin:hub:settings")],
        ]
    )


def _settings_cat_kb(cat: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"admin:settings:edit:{key}")]
        for key, label in SETTING_CATEGORIES.get(cat, [])
    ]
    rows.append([InlineKeyboardButton(text="« تنظیمات", callback_data="admin:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:settings")
async def admin_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await admin_guard(callback):
        return
    settings = get_settings()
    enabled, dh, dm = await get_digest_schedule(session)
    maint = await bot_content.is_maintenance_mode(session)
    await callback.message.edit_text(
        "⚙️ <b>تنظیمات ربات</b>\n\n"
        f"کانال اجباری: {settings.required_channel_id or '—'}\n"
        f"C2C: {'فعال' if settings.c2c_enabled else 'غیرفعال'} | mock={settings.c2c_mock}\n"
        f"گزارش روزانه: {'روشن' if enabled else 'خاموش'} {dh:02d}:{dm:02d}\n"
        f"تعمیر: {'بله' if maint else 'خیر'}\n"
        f"پاداش دعوت: {await bot_content.get_referral_wallet_reward_toman(session):,} تومان",
        reply_markup=_settings_hub_kb(),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:settings:cat:"))
async def admin_settings_category(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await admin_guard(callback):
        return
    cat = callback.data.split(":")[-1]
    labels = dict(SETTING_CATEGORIES.get(cat, []))
    lines = [f"<b>{cat}</b>"]
    for key in labels:
        val = await bot_content.get_setting(session, key)
        lines.append(f"• {labels[key]}: <code>{val or '—'}</code>")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_settings_cat_kb(cat),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:settings:edit:"))
async def admin_settings_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    key = callback.data.split(":", maxsplit=3)[-1]
    await state.set_state(AdminStates.setting_edit)
    await state.update_data(setting_key=key)
    await callback.message.answer(f"مقدار جدید برای <code>{key}</code>:", reply_markup=cancel_fsm_kb(), parse_mode="HTML")
    await safe_callback_answer(callback)


@router.message(AdminStates.setting_edit)
async def admin_settings_edit_apply(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    data = await state.get_data()
    key = data.get("setting_key")
    if not key:
        await state.clear()
        return
    await state.clear()
    value = (message.text or "").strip()
    row = await session.get(Setting, key)
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))
    await session.commit()
    await message.answer(f"✅ ذخیره شد: {key}={value}", reply_markup=_settings_hub_kb())


@router.message(Command("setting_set"))
async def setting_set_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("/setting_set key value")
        return
    key, value = parts[1], parts[2]
    row = await session.get(Setting, key)
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))
    await session.flush()
    await message.answer(f"ذخیره شد: {key}")
