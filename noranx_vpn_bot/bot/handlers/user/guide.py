from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.connect_guide import (
    guide_app_kb_with_download,
    guide_platform_kb_async,
    guide_root_kb_async,
)
from bot.services import guides as guide_svc
from bot.services.connect_guide import APPS, format_app_guide as static_format_app
from bot.utils.telegram import safe_callback_answer

router = Router()


@router.callback_query(F.data == "menu:guide")
async def menu_guide(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.message.edit_text(
        "<b>📖 راهنمای اتصال</b>\n\n"
        "پلتفرم خود را انتخاب کنید. سپس اپ VPN را نصب و لینک اشتراک را import کنید.",
        reply_markup=await guide_root_kb_async(session),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("guide:platform:"))
async def guide_platform(callback: CallbackQuery, session: AsyncSession) -> None:
    platform = callback.data.split(":")[-1]
    text = await guide_svc.format_platform_menu(session, platform)
    await callback.message.edit_text(
        text,
        reply_markup=await guide_platform_kb_async(session, platform),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("guide:app:"))
async def guide_app(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    if len(parts) >= 4:
        app_slug, platform_slug = parts[2], parts[3]
    else:
        app_slug = parts[2]
        platform_slug = "android"
    text = await guide_svc.format_app_guide(session, app_slug, platform_slug)
    app = await guide_svc.get_app_by_slug(session, platform_slug, app_slug)
    download_url = app.download_url if app else ""
    if not app and app_slug in APPS:
        text = static_format_app(app_slug)
    kb = guide_app_kb_with_download(app_slug, platform_slug, download_url)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await safe_callback_answer(callback)
