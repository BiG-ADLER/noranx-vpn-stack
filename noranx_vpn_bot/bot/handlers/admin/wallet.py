from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import AdminAuditLog, TelegramUser, WalletTxType
from bot.keyboards.common import cancel_fsm_kb
from bot.services.payment.wallet import WalletService
from bot.states import AdminStates
from bot.utils.admin_ui import admin_guard
from bot.utils.formatting import format_toman
from bot.utils.telegram import safe_callback_answer

router = Router()
wallet_service = WalletService()


def _wallet_user_kb(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ افزایش", callback_data=f"admin:wallet:add:{tg_id}"),
                InlineKeyboardButton(text="➖ کاهش", callback_data=f"admin:wallet:sub:{tg_id}"),
            ],
            [InlineKeyboardButton(text="« کارت کاربر", callback_data=f"admin:user:view:{tg_id}")],
            [InlineKeyboardButton(text="« تنظیمات", callback_data="admin:hub:settings")],
        ]
    )


@router.callback_query(F.data == "admin:wallet")
async def admin_wallet_menu(callback: CallbackQuery) -> None:
    if not await admin_guard(callback):
        return
    await callback.message.edit_text(
        "💰 <b>مدیریت کیف پول</b>\n"
        "از کارت کاربر یا شناسه تلگرام وارد شوید.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="« تنظیمات", callback_data="admin:hub:settings")],
            ]
        ),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:wallet:user:"))
async def admin_wallet_user(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await admin_guard(callback):
        return
    tg_id = int(callback.data.split(":")[-1])
    user = await session.scalar(select(TelegramUser).where(TelegramUser.telegram_id == tg_id))
    if not user:
        await safe_callback_answer(callback, "کاربر یافت نشد.", show_alert=True)
        return
    await callback.message.edit_text(
        f"💰 کیف پول کاربر <code>{tg_id}</code>\nموجودی: {format_toman(user.wallet_balance_toman)}",
        reply_markup=_wallet_user_kb(tg_id),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.regexp(r"^admin:wallet:(add|sub):\d+$"))
async def admin_wallet_adjust_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    _, _, action, tg_id = callback.data.split(":")
    await state.set_state(AdminStates.wallet_adjust)
    await state.update_data(wallet_action=action, wallet_tg_id=int(tg_id))
    label = "افزایش" if action == "add" else "کاهش"
    await callback.message.answer(f"مبلغ {label} (تومان):", reply_markup=cancel_fsm_kb())
    await safe_callback_answer(callback)


@router.message(AdminStates.wallet_adjust)
async def admin_wallet_adjust_apply(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    data = await state.get_data()
    await state.clear()
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        await message.answer("عدد نامعتبر.")
        return
    tg_id = int(data.get("wallet_tg_id"))
    action = data.get("wallet_action")
    user = await session.scalar(select(TelegramUser).where(TelegramUser.telegram_id == tg_id))
    if not user:
        await message.answer("کاربر یافت نشد.")
        return
    signed = amount if action == "add" else -amount
    bal = await wallet_service.credit(
        session, user.id, signed, WalletTxType.ADMIN_ADJUST, note=f"admin {action}"
    )
    session.add(
        AdminAuditLog(
            admin_telegram_id=message.from_user.id,
            action=f"wallet_{action}",
            details=f"{tg_id} {signed}",
        )
    )
    await session.commit()
    await message.answer(
        f"✅ موجودی جدید: {format_toman(bal)}",
        reply_markup=_wallet_user_kb(tg_id),
    )


@router.message(Command("wallet_add"))
async def wallet_add_cmd(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("/wallet_add telegram_id toman")
        return
    await state.set_state(AdminStates.wallet_adjust)
    await state.update_data(wallet_action="add", wallet_tg_id=int(parts[1]), preset_amount=int(parts[2]))
    await message.answer("تأیید مبلغ یا مقدار جدید:", reply_markup=cancel_fsm_kb())


@router.message(Command("wallet_sub"))
async def wallet_sub_cmd(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("/wallet_sub telegram_id toman")
        return
    await state.set_state(AdminStates.wallet_adjust)
    await state.update_data(wallet_action="sub", wallet_tg_id=int(parts[1]), preset_amount=int(parts[2]))
    await message.answer("تأیید مبلغ یا مقدار جدید:", reply_markup=cancel_fsm_kb())


