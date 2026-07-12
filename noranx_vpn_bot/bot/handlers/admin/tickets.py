import json
from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import (
    SupportMessage,
    SupportTicket,
    SupportTicketNote,
    TelegramUser,
    TicketPriority,
    TicketStatus,
)
from bot.keyboards.common import cancel_fsm_kb
from bot.states import SupportStates
from bot.utils.telegram import safe_callback_answer

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


def _status_badge(status: TicketStatus) -> str:
    mapping = {
        TicketStatus.OPEN: "🟡",
        TicketStatus.ANSWERED: "🟢",
        TicketStatus.IN_PROGRESS: "🔵",
        TicketStatus.WAITING_USER: "🟣",
        TicketStatus.RESOLVED: "✅",
        TicketStatus.CLOSED: "⚫",
    }
    return mapping.get(status, "•")


def _priority_badge(priority: TicketPriority) -> str:
    mapping = {
        TicketPriority.LOW: "⬇️",
        TicketPriority.NORMAL: "▫️",
        TicketPriority.HIGH: "⬆️",
        TicketPriority.URGENT: "🔥",
    }
    return mapping.get(priority, "▫️")


def _tickets_list_kb(tickets: list[SupportTicket], filter_status: str) -> InlineKeyboardMarkup:
    rows = []
    for t in tickets:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{_status_badge(t.status)} #{t.id} {t.title[:24]}",
                    callback_data=f"admin:ticket:view:{t.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="همه", callback_data="admin:tickets:all"),
            InlineKeyboardButton(text="باز", callback_data="admin:tickets:open"),
            InlineKeyboardButton(text="درحال انجام", callback_data="admin:tickets:in_progress"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="منتظر کاربر", callback_data="admin:tickets:waiting_user"),
            InlineKeyboardButton(text="حل‌شده", callback_data="admin:tickets:resolved"),
            InlineKeyboardButton(text="بسته", callback_data="admin:tickets:closed"),
        ]
    )
    rows.append([InlineKeyboardButton(text="« زیرساخت", callback_data="admin:hub:infra")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _ticket_actions_kb(ticket: SupportTicket) -> InlineKeyboardMarkup:
    status_rows = [
        [
            InlineKeyboardButton(text="باز", callback_data=f"admin:ticket:set_status:{ticket.id}:open"),
            InlineKeyboardButton(
                text="درحال انجام", callback_data=f"admin:ticket:set_status:{ticket.id}:in_progress"
            ),
        ],
        [
            InlineKeyboardButton(
                text="منتظر کاربر", callback_data=f"admin:ticket:set_status:{ticket.id}:waiting_user"
            ),
            InlineKeyboardButton(text="حل‌شده", callback_data=f"admin:ticket:set_status:{ticket.id}:resolved"),
        ],
    ]
    rows = [
        [
            InlineKeyboardButton(text="💬 پاسخ کاربر", callback_data=f"admin:ticket:reply:{ticket.id}"),
            InlineKeyboardButton(text="📝 یادداشت داخلی", callback_data=f"admin:ticket:note:{ticket.id}"),
        ],
        [
            InlineKeyboardButton(
                text=f"⏱ SLA {'تنظیم' if not ticket.due_at else 'ویرایش'}",
                callback_data=f"admin:ticket:due:{ticket.id}",
            ),
            InlineKeyboardButton(text="🏷 تگ‌ها", callback_data=f"admin:ticket:tags:{ticket.id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ عنوان", callback_data=f"admin:ticket:title:{ticket.id}"),
            InlineKeyboardButton(text="🗂 دسته", callback_data=f"admin:ticket:category:{ticket.id}"),
        ],
        [
            InlineKeyboardButton(text="👤 تخصیص به من", callback_data=f"admin:ticket:assign_me:{ticket.id}"),
            InlineKeyboardButton(text="🚫 لغو تخصیص", callback_data=f"admin:ticket:assign_none:{ticket.id}"),
        ],
        [
            InlineKeyboardButton(text="⬇️", callback_data=f"admin:ticket:priority:{ticket.id}:low"),
            InlineKeyboardButton(text="▫️", callback_data=f"admin:ticket:priority:{ticket.id}:normal"),
            InlineKeyboardButton(text="⬆️", callback_data=f"admin:ticket:priority:{ticket.id}:high"),
            InlineKeyboardButton(text="🔥", callback_data=f"admin:ticket:priority:{ticket.id}:urgent"),
        ],
        *status_rows,
        [
            InlineKeyboardButton(text="🔒 بستن", callback_data=f"admin:ticket:close:{ticket.id}"),
            InlineKeyboardButton(text="♻️ بازگشایی", callback_data=f"admin:ticket:reopen:{ticket.id}"),
        ],
        [InlineKeyboardButton(text="« لیست تیکت‌ها", callback_data="admin:tickets:all")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _status_filter(status_raw: str):
    if status_raw == "all":
        return None
    try:
        return TicketStatus(status_raw)
    except Exception:
        return TicketStatus.OPEN


async def _render_ticket(ticket: SupportTicket, session: AsyncSession) -> str:
    user = await session.get(TelegramUser, ticket.user_id)
    messages = (
        await session.scalars(
            select(SupportMessage)
            .where(SupportMessage.ticket_id == ticket.id)
            .order_by(SupportMessage.id.desc())
            .limit(5)
        )
    ).all()
    notes = (
        await session.scalars(
            select(SupportTicketNote)
            .where(SupportTicketNote.ticket_id == ticket.id)
            .order_by(SupportTicketNote.id.desc())
            .limit(3)
        )
    ).all()
    tags = []
    if ticket.tags_json:
        try:
            tags = json.loads(ticket.tags_json)
        except Exception:
            tags = []
    lines = [
        f"<b>🎫 تیکت #{ticket.id}</b>",
        f"عنوان: {ticket.title}",
        f"دسته: {ticket.category}",
        f"وضعیت: {ticket.status.value} {_status_badge(ticket.status)}",
        f"اولویت: {ticket.priority.value} {_priority_badge(ticket.priority)}",
        f"کاربر: <code>{user.telegram_id if user else ticket.user_id}</code>",
        f"مسئول: <code>{ticket.assignee_admin_id or '—'}</code>",
        f"تگ‌ها: {', '.join(tags) if tags else '—'}",
        f"SLA: {ticket.due_at.isoformat() if ticket.due_at else '—'}",
        "",
        "<b>آخرین پیام‌ها</b>",
    ]
    for m in messages:
        role = "ادمین" if m.from_admin else "کاربر"
        lines.append(f"• {role}: {m.text[:80]}")
    if notes:
        lines.append("")
        lines.append("<b>یادداشت داخلی</b>")
        for n in notes:
            lines.append(f"• {n.note[:80]}")
    return "\n".join(lines)


async def _refresh_ticket_view(
    callback: CallbackQuery, session: AsyncSession, ticket_id: int
) -> None:
    ticket = await session.get(SupportTicket, ticket_id)
    if not ticket:
        await safe_callback_answer(callback, "یافت نشد.", show_alert=True)
        return
    await callback.message.edit_text(
        await _render_ticket(ticket, session),
        reply_markup=_ticket_actions_kb(ticket),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


async def build_tickets_screen(session: AsyncSession, status_raw: str = "all") -> tuple[str, InlineKeyboardMarkup]:
    status_filter = _status_filter(status_raw)
    q = select(SupportTicket).order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc()).limit(30)
    if status_filter is not None:
        q = q.where(SupportTicket.status == status_filter)
    tickets = (await session.scalars(q)).all()
    return f"🎫 تیکت‌ها (فیلتر: {status_raw})", _tickets_list_kb(list(tickets), status_raw)


@router.callback_query(F.data == "admin:tickets")
@router.callback_query(F.data.startswith("admin:tickets:"))
async def admin_tickets_list(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    status_raw = callback.data.split(":")[-1] if ":" in callback.data else "all"
    text, kb = await build_tickets_screen(session, status_raw)
    await callback.message.edit_text(text, reply_markup=kb)
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:ticket:view:"))
async def admin_ticket_view(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    ticket_id = int(callback.data.split(":")[-1])
    await _refresh_ticket_view(callback, session, ticket_id)


@router.callback_query(F.data.regexp(r"^admin:ticket:set_status:\d+:[a-z_]+$"))
async def admin_ticket_set_status(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    _, _, _, tid, status_raw = callback.data.split(":")
    ticket = await session.get(SupportTicket, int(tid))
    if not ticket:
        await safe_callback_answer(callback, "یافت نشد.", show_alert=True)
        return
    try:
        ticket.status = TicketStatus(status_raw)
    except Exception:
        await safe_callback_answer(callback, "وضعیت نامعتبر.", show_alert=True)
        return
    if ticket.status == TicketStatus.CLOSED:
        ticket.closed_at = datetime.now(UTC)
    await session.commit()
    await _refresh_ticket_view(callback, session, int(tid))


@router.callback_query(F.data.regexp(r"^admin:ticket:priority:\d+:[a-z]+$"))
async def admin_ticket_priority(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    _, _, _, tid, raw = callback.data.split(":")
    ticket = await session.get(SupportTicket, int(tid))
    if not ticket:
        await safe_callback_answer(callback, "یافت نشد.", show_alert=True)
        return
    try:
        ticket.priority = TicketPriority(raw)
    except Exception:
        await safe_callback_answer(callback, "اولویت نامعتبر.", show_alert=True)
        return
    await session.commit()
    await _refresh_ticket_view(callback, session, int(tid))


@router.callback_query(F.data.startswith("admin:ticket:assign_me:"))
async def admin_ticket_assign_me(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    tid = int(callback.data.split(":")[-1])
    ticket = await session.get(SupportTicket, tid)
    if ticket:
        ticket.assignee_admin_id = callback.from_user.id
        ticket.status = TicketStatus.IN_PROGRESS
        await session.commit()
    await _refresh_ticket_view(callback, session, tid)


@router.callback_query(F.data.startswith("admin:ticket:assign_none:"))
async def admin_ticket_assign_none(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    tid = int(callback.data.split(":")[-1])
    ticket = await session.get(SupportTicket, tid)
    if ticket:
        ticket.assignee_admin_id = None
        await session.commit()
    await _refresh_ticket_view(callback, session, tid)


@router.callback_query(F.data.startswith("admin:ticket:close:"))
async def admin_ticket_close(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    tid = int(callback.data.split(":")[-1])
    ticket = await session.get(SupportTicket, tid)
    if ticket:
        ticket.status = TicketStatus.CLOSED
        ticket.closed_at = datetime.now(UTC)
        await session.commit()
    await _refresh_ticket_view(callback, session, tid)


@router.callback_query(F.data.startswith("admin:ticket:reopen:"))
async def admin_ticket_reopen(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    tid = int(callback.data.split(":")[-1])
    ticket = await session.get(SupportTicket, tid)
    if ticket:
        ticket.status = TicketStatus.OPEN
        ticket.closed_at = None
        await session.commit()
    await _refresh_ticket_view(callback, session, tid)


@router.callback_query(F.data.regexp(r"^admin:ticket:(reply|note|title|category|tags|due):\d+$"))
async def admin_ticket_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    _, _, action, tid = callback.data.split(":")
    await state.set_state(SupportStates.admin_reply)
    await state.update_data(ticket_id=int(tid), ticket_action=action)
    prompts = {
        "reply": "پاسخ به کاربر را بنویسید:",
        "note": "یادداشت داخلی را بنویسید:",
        "title": "عنوان جدید:",
        "category": "دسته جدید (connection/payment/other):",
        "tags": "تگ‌ها با کاما (مثال: vip,urgent):",
        "due": "مهلت SLA به ساعت (مثال: 24):",
    }
    await callback.message.answer(
        prompts.get(action, "مقدار جدید:"),
        reply_markup=cancel_fsm_kb(),
    )
    await safe_callback_answer(callback)


@router.message(SupportStates.admin_reply)
async def admin_ticket_reply(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    action = data.get("ticket_action")
    await state.clear()
    ticket = await session.get(SupportTicket, ticket_id)
    if not ticket:
        await message.answer("تیکت یافت نشد.")
        return

    txt = (message.text or "").strip()
    if action == "reply":
        session.add(SupportMessage(ticket_id=ticket_id, from_admin=True, text=txt))
        ticket.status = TicketStatus.WAITING_USER
        user = await session.get(TelegramUser, ticket.user_id)
        if user:
            try:
                await message.bot.send_message(user.telegram_id, f"📩 پاسخ تیکت #{ticket_id}:\n\n{txt}")
            except Exception:
                pass
    elif action == "note":
        session.add(
            SupportTicketNote(
                ticket_id=ticket_id,
                admin_telegram_id=message.from_user.id,
                note=txt,
            )
        )
    elif action == "title":
        ticket.title = txt[:255] if txt else ticket.title
    elif action == "category":
        ticket.category = txt or ticket.category
    elif action == "tags":
        tags = [x.strip() for x in txt.split(",") if x.strip()]
        ticket.tags_json = json.dumps(tags, ensure_ascii=False)
    elif action == "due":
        if txt.isdigit():
            ticket.due_at = datetime.now(UTC) + timedelta(hours=int(txt))

    await session.commit()
    refreshed = await session.get(SupportTicket, ticket_id)
    if refreshed:
        await message.answer(
            await _render_ticket(refreshed, session),
            reply_markup=_ticket_actions_kb(refreshed),
            parse_mode="HTML",
        )
    else:
        await message.answer("✅ ثبت شد.")
