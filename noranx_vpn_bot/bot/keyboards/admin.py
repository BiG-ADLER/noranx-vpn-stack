from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import Payment, PaymentStatus
from bot.keyboards.admin_hubs import admin_root_kb
from bot.services.admin_ops import OpsSnapshot, badge


def admin_menu_kb(snapshot: OpsSnapshot | None = None) -> InlineKeyboardMarkup:
    return admin_root_kb(snapshot)


def c2c_payments_kb(payments: list[Payment], labels: dict[int, str] | None = None) -> InlineKeyboardMarkup:
    labels = labels or {}
    rows = []
    for p in payments:
        label = labels.get(p.id, "")
        if p.status == PaymentStatus.PENDING_REVIEW:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🔍 #{p.id}{label}",
                        callback_data=f"admin:c2c:view:{p.id}",
                    ),
                    InlineKeyboardButton(
                        text="✅",
                        callback_data=f"admin:c2c:approve:{p.id}",
                    ),
                    InlineKeyboardButton(
                        text="❌",
                        callback_data=f"admin:c2c:reject:{p.id}",
                    ),
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"⏳ #{p.id}{label}",
                        callback_data=f"admin:c2c:view:{p.id}",
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text="« زیرساخت", callback_data="admin:hub:infra")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_tickets_kb(ticket_ids: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"#{tid} — {status}", callback_data=f"admin:ticket:view:{tid}")]
        for tid, status in ticket_ids
    ]
    rows.append([InlineKeyboardButton(text="« زیرساخت", callback_data="admin:hub:infra")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_orders_kb(order_ids: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🔄 #{oid}",
                callback_data=f"admin:order:retry:{oid}",
            ),
            InlineKeyboardButton(
                text=f"📜 #{oid}",
                callback_data=f"admin:order:logs:{oid}",
            ),
        ]
        for oid in order_ids
    ]
    rows.append([InlineKeyboardButton(text="« زیرساخت", callback_data="admin:hub:infra")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
