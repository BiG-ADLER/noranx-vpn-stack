from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.admin.users import _is_admin
from bot.keyboards.common import back_to_admin_kb, cancel_fsm_kb
from bot.services.notification_hub import NotificationHub
from bot.states import AdminStates
from bot.utils.telegram import safe_callback_answer

router = Router()


def _messaging_hub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 کانال اصلی", callback_data="admin:msg:channel")],
            [InlineKeyboardButton(text="« کاربران", callback_data="admin:hub:users")],
        ]
    )


@router.callback_query(F.data == "admin:messaging")
@router.callback_query(F.data == "admin:broadcast")
@router.message(Command("broadcast"))
async def messaging_hub(event: Message | CallbackQuery, state: FSMContext) -> None:
    user_id = event.from_user.id
    if not _is_admin(user_id):
        if isinstance(event, CallbackQuery):
            await safe_callback_answer(event, "دسترسی ندارید.", show_alert=True)
        return
    await state.clear()
    text = (
        "📢 <b>مرکز اطلاع‌رسانی</b>\n"
        "ارسال مستقیم به کاربران غیرفعال شده است.\n"
        "فقط انتشار در کانال اصلی مجاز است."
    )
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=_messaging_hub_kb(), parse_mode="HTML")
        await safe_callback_answer(event)
    else:
        await event.answer(text, reply_markup=_messaging_hub_kb(), parse_mode="HTML")


@router.callback_query(F.data == "admin:msg:channel")
async def msg_channel_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return
    await state.update_data(msg_target="channel")
    await state.set_state(AdminStates.messaging_compose)
    await callback.message.edit_text("متن پست کانال:", reply_markup=cancel_fsm_kb())
    await safe_callback_answer(callback)


@router.message(AdminStates.messaging_compose)
async def msg_compose(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    photo_id = message.photo[-1].file_id if message.photo else None
    text = message.text or message.caption or ""
    if not text and not photo_id:
        await message.answer("متن یا عکس لازم است.")
        return

    await state.update_data(msg_text=text, msg_photo=photo_id)
    await state.set_state(AdminStates.messaging_confirm)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ انتشار", callback_data="admin:msg:confirm"),
                InlineKeyboardButton(text="❌ لغو", callback_data="fsm:cancel"),
            ]
        ]
    )
    await message.answer(f"پیش‌نمایش کانال:\n\n{text[:500]}", reply_markup=kb)


@router.callback_query(F.data == "admin:msg:confirm")
async def msg_confirm(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    data = await state.get_data()
    hub = NotificationHub(callback.bot, session)
    ok = await hub.notify_announcement_channel(
        data.get("msg_text", ""),
        photo_file_id=data.get("msg_photo"),
    )
    await state.clear()
    await callback.message.edit_text(
        "✅ در کانال منتشر شد." if ok else "❌ خطا در ارسال به کانال.",
        reply_markup=back_to_admin_kb(),
    )
    await safe_callback_answer(callback)


@router.message(Command("audience_count"))
async def audience_count_cmd(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await message.answer(
        "ارسال مستقیم به کاربران غیرفعال است.\n"
        "این دستور در سیاست فعلی استفاده نمی‌شود."
    )
