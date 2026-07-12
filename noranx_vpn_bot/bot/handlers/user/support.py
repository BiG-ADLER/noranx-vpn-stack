from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import SupportMessage, SupportTicket, TelegramUser, TicketStatus
from bot.keyboards.common import cancel_fsm_kb
from bot.keyboards.user import back_main_kb
from bot.states import SupportStates

router = Router()


def support_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ تیکت جدید", callback_data="support:new")],
            [InlineKeyboardButton(text="📋 تیکت‌های من", callback_data="support:my_tickets")],
            [InlineKeyboardButton(text="« منو", callback_data="menu:main")],
        ]
    )


def support_category_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="اتصال", callback_data="support:cat:connection")],
            [InlineKeyboardButton(text="پرداخت", callback_data="support:cat:payment")],
            [InlineKeyboardButton(text="سایر", callback_data="support:cat:other")],
            [InlineKeyboardButton(text="« بازگشت", callback_data="menu:support")],
        ]
    )


def my_tickets_kb(tickets: list[SupportTicket]) -> InlineKeyboardMarkup:
    status_icon = {
        "open": "🟡",
        "answered": "🟢",
        "in_progress": "🔵",
        "waiting_user": "🟣",
        "resolved": "✅",
        "closed": "⚫",
    }
    rows = [
        [
            InlineKeyboardButton(
                text=f"{status_icon.get(t.status.value, '•')} #{t.id} — {t.title[:20]}",
                callback_data=f"support:view:{t.id}",
            )
        ]
        for t in tickets
    ]
    rows.append([InlineKeyboardButton(text="« پشتیبانی", callback_data="menu:support")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ticket_thread_kb(ticket_id: int, can_reply: bool) -> InlineKeyboardMarkup:
    rows = []
    if can_reply:
        rows.append(
            [InlineKeyboardButton(text="💬 پاسخ", callback_data=f"support:reply:{ticket_id}")]
        )
    rows.append([InlineKeyboardButton(text="« تیکت‌ها", callback_data="support:my_tickets")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "menu:support")
async def support_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "🎫 <b>پشتیبانی</b>\n\nتیکت جدید بسازید یا تیکت‌های قبلی را ببینید.",
        reply_markup=support_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "support:new")
async def support_new(callback: CallbackQuery) -> None:
    await callback.message.edit_text("دسته‌بندی مشکل:", reply_markup=support_category_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("support:cat:"))
async def support_category(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[-1]
    await state.update_data(category=cat)
    await state.set_state(SupportStates.waiting_message)
    await callback.message.answer("عنوان کوتاه مشکل را بنویسید:")
    await state.set_state(SupportStates.waiting_category)
    await callback.answer()


@router.message(SupportStates.waiting_category)
async def support_title(message: Message, state: FSMContext) -> None:
    await state.update_data(ticket_title=(message.text or "").strip()[:120] or "درخواست پشتیبانی")
    await state.set_state(SupportStates.waiting_message)
    await message.answer("شرح مشکل را بنویسید:", reply_markup=cancel_fsm_kb())


@router.message(SupportStates.waiting_message)
async def support_message(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    await state.clear()
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == message.from_user.id)
    )
    if not user:
        await message.answer("ابتدا /start بزنید.")
        return
    ticket = SupportTicket(
        user_id=user.id,
        category=data.get("category", "other"),
        title=data.get("ticket_title", "درخواست پشتیبانی"),
        status=TicketStatus.OPEN,
    )
    session.add(ticket)
    await session.flush()
    session.add(
        SupportMessage(ticket_id=ticket.id, from_admin=False, text=message.text or "")
    )
    await session.flush()

    settings = get_settings()
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                f"🎫 تیکت #{ticket.id} — {ticket.title}\n"
                f"از: {message.from_user.id}\n\n{message.text}",
            )
        except Exception:
            pass

    await message.answer(
        f"✅ تیکت #{ticket.id} ثبت شد. به زودی پاسخ می‌دهیم.",
        reply_markup=back_main_kb(),
    )


@router.callback_query(F.data == "support:my_tickets")
async def support_my_tickets(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not user:
        await callback.answer("ابتدا /start بزنید.", show_alert=True)
        return
    tickets = (
        await session.scalars(
            select(SupportTicket)
            .where(SupportTicket.user_id == user.id)
            .order_by(SupportTicket.id.desc())
            .limit(15)
        )
    ).all()
    if not tickets:
        await callback.message.edit_text(
            "تیکتی ندارید.",
            reply_markup=support_menu_kb(),
        )
    else:
        await callback.message.edit_text(
            "📋 تیکت‌های شما:",
            reply_markup=my_tickets_kb(list(tickets)),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("support:view:"))
async def support_view_ticket(callback: CallbackQuery, session: AsyncSession) -> None:
    ticket_id = int(callback.data.split(":")[-1])
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    ticket = await session.get(SupportTicket, ticket_id)
    if not ticket or not user or ticket.user_id != user.id:
        await callback.answer("یافت نشد.", show_alert=True)
        return
    msgs = (
        await session.scalars(
            select(SupportMessage)
            .where(SupportMessage.ticket_id == ticket_id)
            .order_by(SupportMessage.id)
        )
    ).all()
    text = (
        f"🎫 تیکت #{ticket_id}\n"
        f"عنوان: {ticket.title}\n"
        f"وضعیت: {ticket.status.value}\n\n"
    )
    text += "\n".join(
        f"{'پشتیبانی' if m.from_admin else 'شما'}: {m.text}" for m in msgs
    )
    can_reply = ticket.status not in (TicketStatus.CLOSED, TicketStatus.RESOLVED)
    await callback.message.edit_text(
        text, reply_markup=ticket_thread_kb(ticket_id, can_reply)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("support:reply:"))
async def support_reply_start(callback: CallbackQuery, state: FSMContext) -> None:
    ticket_id = int(callback.data.split(":")[-1])
    await state.set_state(SupportStates.user_reply)
    await state.update_data(ticket_id=ticket_id)
    await callback.message.answer(f"پاسخ خود به تیکت #{ticket_id}:")
    await callback.answer()


@router.message(SupportStates.user_reply)
async def support_user_reply(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    await state.clear()
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == message.from_user.id)
    )
    ticket = await session.get(SupportTicket, ticket_id)
    if not ticket or not user or ticket.user_id != user.id:
        await message.answer("تیکت یافت نشد.")
        return
    if ticket.status in (TicketStatus.CLOSED, TicketStatus.RESOLVED):
        await message.answer("این تیکت بسته شده است. برای ادامه، تیکت جدید بسازید.")
        return
    session.add(
        SupportMessage(ticket_id=ticket_id, from_admin=False, text=message.text or "")
    )
    ticket.status = TicketStatus.OPEN
    await session.flush()
    settings = get_settings()
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                f"💬 پاسخ کاربر در تیکت #{ticket_id}:\n{message.text}",
            )
        except Exception:
            pass
    await message.answer(f"✅ پاسخ شما به تیکت #{ticket_id} ثبت شد.", reply_markup=back_main_kb())
