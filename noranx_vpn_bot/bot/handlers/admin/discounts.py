from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import DiscountCode, DiscountType
from bot.keyboards.common import cancel_fsm_kb
from bot.states import AdminStates
from bot.utils.admin_ui import admin_guard
from bot.utils.telegram import safe_callback_answer
from bot.utils.username import generate_discount_code

router = Router()


def _discounts_list_kb(codes: list[DiscountCode]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if c.is_active else '⛔'} {c.code} — {c.value}{'%' if c.discount_type == DiscountType.PERCENT else 'ت'}",
                callback_data=f"admin:discount:view:{c.id}",
            )
        ]
        for c in codes
    ]
    rows.append([InlineKeyboardButton(text="➕ کد جدید", callback_data="admin:discount:create")])
    rows.append([InlineKeyboardButton(text="« فروش", callback_data="admin:hub:commerce")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _discount_actions_kb(discount_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔀 فعال/غیرفعال", callback_data=f"admin:discount:toggle:{discount_id}"),
            ],
            [InlineKeyboardButton(text="« تخفیف‌ها", callback_data="admin:discounts")],
        ]
    )


@router.callback_query(F.data == "admin:discounts")
async def admin_discounts(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await admin_guard(callback):
        return
    codes = (
        await session.scalars(select(DiscountCode).order_by(DiscountCode.id.desc()).limit(30))
    ).all()
    await callback.message.edit_text(
        "🏷 <b>کدهای تخفیف</b>",
        reply_markup=_discounts_list_kb(list(codes)),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:discount:view:"))
async def admin_discount_view(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await admin_guard(callback):
        return
    did = int(callback.data.split(":")[-1])
    dc = await session.get(DiscountCode, did)
    if not dc:
        await safe_callback_answer(callback, "یافت نشد.", show_alert=True)
        return
    await callback.message.edit_text(
        f"🏷 کد: <code>{dc.code}</code>\n"
        f"نوع: {dc.discount_type.value}\n"
        f"مقدار: {dc.value}\n"
        f"استفاده: {dc.used_count}/{dc.max_uses}\n"
        f"وضعیت: {'فعال' if dc.is_active else 'غیرفعال'}\n"
        f"اعتبار تا: {dc.valid_until.isoformat() if dc.valid_until else '—'}",
        reply_markup=_discount_actions_kb(dc.id),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data == "admin:discount:create")
async def admin_discount_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.set_state(AdminStates.create_discount)
    await callback.message.answer(
        "درصد تخفیف و حداکثر استفاده را وارد کنید:\nمثال: 15 10",
        reply_markup=cancel_fsm_kb(),
    )
    await safe_callback_answer(callback)


@router.message(AdminStates.create_discount)
async def admin_discount_create(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    await state.clear()
    parts = (message.text or "").split()
    try:
        percent = int(parts[0])
        max_uses = int(parts[1]) if len(parts) > 1 else 100
    except (IndexError, ValueError):
        await message.answer("فرمت: درصد [max_uses]\nمثال: 15 10")
        return
    code = generate_discount_code()
    dc = DiscountCode(
        code=code,
        discount_type=DiscountType.PERCENT,
        value=percent,
        max_uses=max_uses,
        valid_until=datetime.now(UTC) + timedelta(days=90),
    )
    session.add(dc)
    await session.flush()
    await message.answer(
        f"✅ کد ساخته شد: <code>{code}</code> — {percent}% — {max_uses} استفاده",
        reply_markup=_discount_actions_kb(dc.id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:discount:toggle:"))
async def admin_discount_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await admin_guard(callback):
        return
    did = int(callback.data.split(":")[-1])
    dc = await session.get(DiscountCode, did)
    if not dc:
        await safe_callback_answer(callback, "یافت نشد.", show_alert=True)
        return
    dc.is_active = not dc.is_active
    await session.commit()
    await admin_discount_view(callback, session)


@router.message(Command("discount_new"))
async def discount_new_cmd(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    await state.set_state(AdminStates.create_discount)
    await message.answer("درصد و max_uses:\nمثال: 15 10", reply_markup=cancel_fsm_kb())
