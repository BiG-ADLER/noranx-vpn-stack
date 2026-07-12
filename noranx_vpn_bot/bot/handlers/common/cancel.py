from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import get_settings
from bot.keyboards.common import back_to_admin_kb
from bot.keyboards.user import main_menu_kb
from bot.services.channel_gate import is_channel_member, is_exempt, send_gate_screen

router = Router()


@router.message(Command("cancel"))
@router.callback_query(F.data == "fsm:cancel")
async def cancel_fsm(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    settings = get_settings()
    is_admin = event.from_user.id in settings.admin_ids
    user_id = event.from_user.id
    bot = event.bot

    if not is_exempt(user_id) and not await is_channel_member(bot, user_id):
        if isinstance(event, CallbackQuery):
            await event.answer()
            if event.message:
                await send_gate_screen(bot, event.message.chat.id, edit_message=event.message)
            return
        await event.answer("عملیات لغو شد.")
        await send_gate_screen(bot, event.chat.id)
        return

    text = "عملیات لغو شد."
    if isinstance(event, CallbackQuery):
        kb = back_to_admin_kb() if is_admin else main_menu_kb(is_admin)
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        kb = main_menu_kb(is_admin)
        await event.answer(text, reply_markup=kb)
