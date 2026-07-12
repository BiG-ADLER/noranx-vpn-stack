from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import GuideApp, GuidePlatform, GuideStep
from bot.handlers.admin.users import _is_admin
from bot.keyboards.admin_hubs import content_hub_kb
from bot.keyboards.common import back_to_admin_kb, cancel_fsm_kb
from bot.services import guides as guide_svc
from bot.states import AdminStates
from bot.utils.telegram import safe_callback_answer

router = Router()


@router.callback_query(F.data == "admin:hub:content")
async def content_hub(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    await callback.message.edit_text("📖 <b>راهنما و محتوا</b>", reply_markup=content_hub_kb(), parse_mode="HTML")
    await safe_callback_answer(callback)


@router.callback_query(F.data == "admin:guides")
async def guides_root(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    platforms = await guide_svc.list_platforms(session, active_only=False)
    rows = [
        [InlineKeyboardButton(text=f"{'✅' if p.is_active else '⛔'} {p.title_fa}", callback_data=f"admin:guide:plat:{p.id}")]
        for p in platforms
    ]
    rows.append([InlineKeyboardButton(text="« محتوا", callback_data="admin:hub:content")])
    await callback.message.edit_text(
        "📖 <b>مدیریت راهنمای اتصال</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:guide:plat:"))
async def guide_platform(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    pid = int(callback.data.split(":")[-1])
    platform = await guide_svc.get_platform(session, pid)
    if not platform:
        return
    apps = await guide_svc.list_apps_for_platform(session, pid, active_only=False)
    rows = [
        [InlineKeyboardButton(text=a.title_fa, callback_data=f"admin:guide:app:{a.id}")]
        for a in apps
    ]
    rows.append([InlineKeyboardButton(text="« پلتفرم‌ها", callback_data="admin:guides")])
    await callback.message.edit_text(
        f"<b>{platform.title_fa}</b> — اپ‌ها:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:guide:app:"))
async def guide_app_admin(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    app_id = int(callback.data.split(":")[-1])
    app = await guide_svc.get_app(session, app_id)
    if not app:
        return
    text = guide_svc.format_app_from_db(app)
    rows = [
        [InlineKeyboardButton(text="👁 پیش‌نمایش", callback_data=f"admin:guide:preview:{app_id}")],
        [InlineKeyboardButton(text="✏️ ویرایش عنوان", callback_data=f"admin:guide:edit:title:{app_id}")],
        [InlineKeyboardButton(text="🔗 لینک دانلود", callback_data=f"admin:guide:edit:url:{app_id}")],
        [InlineKeyboardButton(text="« اپ‌ها", callback_data=f"admin:guide:plat:{app.platform_id}")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:guide:preview:"))
async def guide_preview(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    app_id = int(callback.data.split(":")[-1])
    app = await guide_svc.get_app(session, app_id)
    if app:
        await callback.message.answer(guide_svc.format_app_from_db(app), parse_mode="HTML")
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:guide:edit:"))
async def guide_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return
    _, _, _, field, app_id = callback.data.split(":", 4)
    await state.set_state(AdminStates.guide_edit_text)
    await state.update_data(guide_app_id=int(app_id), guide_field=field)
    label = "عنوان" if field == "title" else "لینک دانلود"
    await callback.message.edit_text(f"{label} جدید:", reply_markup=cancel_fsm_kb())
    await safe_callback_answer(callback)


@router.message(AdminStates.guide_edit_text)
async def guide_edit_save(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    app = await guide_svc.get_app(session, data["guide_app_id"])
    if not app:
        await message.answer("اپ یافت نشد.")
        await state.clear()
        return
    val = message.text.strip()
    if data["guide_field"] == "title":
        app.title_fa = val
    else:
        app.download_url = val
    await guide_svc.audit_guide(session, message.from_user.id, "guide_edit", f"app={app.id}")
    await session.commit()
    await state.clear()
    await message.answer("✅ ذخیره شد.", reply_markup=back_to_admin_kb())
