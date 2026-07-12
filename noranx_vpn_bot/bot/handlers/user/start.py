from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.keyboards.admin import admin_menu_kb
from bot.keyboards.admin_reply import ADMIN_REPLY_LABELS, admin_reply_kb
from bot.keyboards.user import main_menu_kb
from bot.handlers.user.channel_gate import _show_welcome
from bot.services import bot_content
from bot.services.admin_ops import build_ops_snapshot
from bot.services.channel_gate import is_channel_member, is_exempt, send_gate_screen
from bot.services.notification_hub import NotificationHub
from bot.services.referral import ReferralService
from bot.services.users import UserService
from bot.utils.telegram import safe_callback_answer

router = Router()
user_service = UserService()
referral_service = ReferralService()

ADMIN_REPLY_ROUTES = {
    "📥 صندوق": "admin:inbox",
    "💳 C2C": "admin:payments",
    "🎫 تیکت": "admin:tickets",
    "🔍 دیباگ": "admin:debug",
    "📚 راهنما": "admin:help",
}


async def _admin_panel_text(session: AsyncSession) -> str:
    return await bot_content.get_admin_panel_title(session)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    settings = get_settings()
    ref_code = None
    if message.text and len(message.text.split()) > 1:
        ref_code = message.text.split(maxsplit=1)[1]

    user, created = await user_service.get_or_create(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        referral_code_from_start=ref_code,
    )
    if created:
        hub = NotificationHub(message.bot, session)
        await hub.notify_new_user(message.from_user.id, message.from_user.username)
        await session.commit()

    is_admin = message.from_user.id in settings.admin_ids
    user_id = message.from_user.id

    if not is_exempt(user_id) and not await is_channel_member(message.bot, user_id):
        await send_gate_screen(message.bot, message.chat.id)
        return

    if user:
        await referral_service.try_credit_referrer(session, message.bot, user)

    await _show_welcome(
        message,
        session,
        user=user,
        created=created,
        is_admin=is_admin,
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession, state: FSMContext) -> None:
    settings = get_settings()
    if message.from_user.id not in settings.admin_ids:
        return
    await state.clear()
    snapshot = await build_ops_snapshot(session)
    await message.answer(
        await _admin_panel_text(session),
        reply_markup=admin_menu_kb(snapshot),
    )
    await message.answer("میانبر ادمین:", reply_markup=admin_reply_kb())


@router.message(F.text.in_(ADMIN_REPLY_ROUTES.keys()))
async def admin_reply_shortcuts(message: Message, session: AsyncSession) -> None:
    settings = get_settings()
    if message.from_user.id not in settings.admin_ids:
        return
    route = ADMIN_REPLY_ROUTES[message.text]
    snapshot = await build_ops_snapshot(session)
    if route == "admin:inbox":
        from bot.keyboards.admin_inbox import inbox_kb
        from bot.services.admin_ops import format_ops_inbox_text

        await message.answer(
            format_ops_inbox_text(snapshot),
            reply_markup=inbox_kb(snapshot),
            parse_mode="HTML",
        )
        return
    if route == "admin:help":
        from bot.handlers.admin.help import _render_hub

        text, kb = await _render_hub(session)
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return
    if route == "admin:debug":
        from bot.handlers.admin.debug import build_debug_report
        from bot.keyboards.admin_inbox import debug_actions_kb

        report = await build_debug_report(session)
        await message.answer(report, reply_markup=debug_actions_kb(), parse_mode="HTML")
        return
    if route == "admin:payments":
        from bot.handlers.admin.payments import build_payments_screen

        text, kb = await build_payments_screen(session)
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return
    if route == "admin:tickets":
        from bot.handlers.admin.tickets import build_tickets_screen

        text, kb = await build_tickets_screen(session, "all")
        await message.answer(text, reply_markup=kb)
        return
    await message.answer("از دکمه‌های زیر استفاده کنید:", reply_markup=admin_menu_kb(snapshot))


@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery, session: AsyncSession) -> None:
    settings = get_settings()
    is_admin = callback.from_user.id in settings.admin_ids
    await callback.message.edit_text(
        "منوی اصلی:",
        reply_markup=main_menu_kb(is_admin),
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data == "menu:admin")
async def menu_admin(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    settings = get_settings()
    if callback.from_user.id not in settings.admin_ids:
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    await state.clear()
    snapshot = await build_ops_snapshot(session)
    await callback.message.edit_text(
        await _admin_panel_text(session),
        reply_markup=admin_menu_kb(snapshot),
    )
    await safe_callback_answer(callback)
