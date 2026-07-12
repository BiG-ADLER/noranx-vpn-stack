from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.admin.users import _is_admin
from bot.jobs.registry import reschedule_digest, send_digest_now
from bot.keyboards.admin_hubs import settings_hub_kb
from bot.keyboards.common import back_to_admin_kb, cancel_fsm_kb
from bot.services import bot_content
from bot.services.reports import get_digest_schedule
from bot.states import AdminStates
from bot.utils.telegram import safe_callback_answer

router = Router()


@router.callback_query(F.data == "admin:hub:settings")
async def settings_hub(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        "⚙️ <b>تنظیمات و گزارش</b>",
        reply_markup=settings_hub_kb(),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data == "admin:hub:infra")
async def infra_hub(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    from bot.keyboards.admin_hubs import infra_hub_kb

    await callback.message.edit_text("🖥 <b>زیرساخت</b>", reply_markup=infra_hub_kb(), parse_mode="HTML")
    await safe_callback_answer(callback)


@router.callback_query(F.data == "admin:ops:report")
async def report_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    enabled, hour, minute = await get_digest_schedule(session)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'✅' if enabled else '⛔'} فعال/غیرفعال",
                    callback_data="admin:ops:report:toggle",
                )
            ],
            [
                InlineKeyboardButton(text="🕘 ۰۸:۰۰", callback_data="admin:ops:report:time:8:0"),
                InlineKeyboardButton(text="🕘 ۰۹:۰۰", callback_data="admin:ops:report:time:9:0"),
            ],
            [
                InlineKeyboardButton(text="🕘 ۱۰:۰۰", callback_data="admin:ops:report:time:10:0"),
                InlineKeyboardButton(text="🕘 ۲۱:۰۰", callback_data="admin:ops:report:time:21:0"),
            ],
            [InlineKeyboardButton(text="📤 ارسال الان", callback_data="admin:ops:report:now")],
            [InlineKeyboardButton(text="« تنظیمات", callback_data="admin:hub:settings")],
        ]
    )
    await callback.message.edit_text(
        f"📊 <b>گزارش روزانه</b> (تهران)\n"
        f"وضعیت: {'فعال' if enabled else 'غیرفعال'}\n"
        f"زمان: <code>{hour:02d}:{minute:02d}</code>",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data == "admin:ops:report:toggle")
async def report_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    enabled, hour, minute = await get_digest_schedule(session)
    await bot_content.set_setting(session, "ops_digest_enabled", "false" if enabled else "true")
    await session.commit()
    reschedule_digest(hour, minute, enabled=not enabled)
    await report_settings(callback, session)


@router.callback_query(F.data.startswith("admin:ops:report:time:"))
async def report_time(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    _, _, _, _, h, m = callback.data.split(":")
    await bot_content.set_setting(session, "ops_digest_hour", h)
    await bot_content.set_setting(session, "ops_digest_minute", m)
    await session.commit()
    enabled, _, _ = await get_digest_schedule(session)
    reschedule_digest(int(h), int(m), enabled=enabled)
    await report_settings(callback, session)


@router.callback_query(F.data == "admin:ops:report:now")
async def report_now_cb(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    await send_digest_now(callback.bot)
    await safe_callback_answer(callback, "گزارش ارسال شد.")


@router.message(Command("report_now"))
async def report_now_cmd(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await send_digest_now(message.bot)
    await message.answer("گزارش ارسال شد.")


@router.message(Command("report_schedule"))
async def report_schedule_cmd(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("استفاده: /report_schedule 9 30")
        return
    hour, minute = int(parts[1]), int(parts[2])
    await bot_content.set_setting(session, "ops_digest_hour", str(hour))
    await bot_content.set_setting(session, "ops_digest_minute", str(minute))
    await session.commit()
    enabled, _, _ = await get_digest_schedule(session)
    reschedule_digest(hour, minute, enabled=enabled)
    await message.answer(f"زمان گزارش: {hour:02d}:{minute:02d} تهران")
