from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.handlers.admin.users import _is_admin
from bot.keyboards.admin_help import help_commands_kb, help_hub_kb, help_section_kb
from bot.services.admin_help_catalog import (
    SECTIONS,
    find_section,
    format_commands_page,
    format_section,
)
from bot.services.admin_help_stats import build_quick_stats
from bot.utils.telegram import safe_callback_answer

router = Router()


async def _render_hub(session: AsyncSession) -> tuple[str, object]:
    stats = await build_quick_stats(session)
    text = (
        "<b>📚 راهنمای پنل ادمین NoranX</b>\n\n"
        f"{stats}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>دسترسی سریع</b>\n"
        "بخش مورد نظر را انتخاب کنید یا <code>/help limiter</code> برای پرش مستقیم.\n\n"
        "<b>میانبرها</b>\n"
        "• <code>/admin</code> — پنل مدیریت\n"
        "• <code>/help</code> — همین صفحه\n"
        "• <code>/debug</code> — گزارش سلامت کامل"
    )
    return text, help_hub_kb()


@router.callback_query(F.data == "admin:help")
async def admin_help_hub(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    text, kb = await _render_hub(session)
    await callback.message.edit_text(text, reply_markup=kb)
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:help:section:"))
async def admin_help_section(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    section_id = callback.data.split(":")[-1]
    if section_id not in SECTIONS:
        await safe_callback_answer(callback, "بخش یافت نشد.", show_alert=True)
        return
    text = format_section(section_id)
    await callback.message.edit_text(text, reply_markup=help_section_kb(section_id))
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:help:commands:"))
async def admin_help_commands(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    page = int(callback.data.split(":")[-1])
    text, total_pages = format_commands_page(page)
    await callback.message.edit_text(
        text,
        reply_markup=help_commands_kb(page, total_pages),
    )
    await safe_callback_answer(callback)


@router.message(Command("help"))
@router.message(Command("admin_help"))
async def admin_help_cmd(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        section_id = find_section(parts[1])
        if section_id:
            text = format_section(section_id)
            await message.answer(text, reply_markup=help_section_kb(section_id))
            return
    text, kb = await _render_hub(session)
    await message.answer(text, reply_markup=kb)
