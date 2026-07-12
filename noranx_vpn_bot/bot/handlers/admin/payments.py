from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import AdminAuditLog, Payment, PaymentProvider, PaymentStatus, TelegramUser
from bot.handlers.user.shop import _get_services
from bot.keyboards.admin import admin_menu_kb, c2c_payments_kb
from bot.services.payment.c2c_utils import parse_metadata, update_metadata
from bot.services.payment.completion import (
    complete_payment,
    notify_order_fulfilled,
    notify_wallet_credited,
)
from bot.services.payment.wallet import WalletService
from bot.keyboards.common import cancel_fsm_kb
from bot.states import AdminStates
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bot.services.admin_ops import build_ops_snapshot
from bot.utils.formatting import format_relative_time, format_toman
from bot.utils.logging import get_logger

logger = get_logger("c2c")

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


async def _approve_payment(callback: CallbackQuery, session: AsyncSession, payment_id: int) -> str:
    payment = await session.get(Payment, payment_id)
    if not payment or payment.provider != PaymentProvider.C2C:
        return "پرداخت یافت نشد."

    if payment.status == PaymentStatus.COMPLETED:
        return "قبلاً تأیید شده."

    if payment.status not in (PaymentStatus.PENDING_REVIEW, PaymentStatus.PENDING):
        return f"وضعیت نامعتبر: {payment.status.value}"

    svc = _get_services()
    result = await complete_payment(
        session,
        payment,
        order_service=svc,
        wallet=WalletService(),
        source="admin_approve",
    )
    if result.error:
        return f"خطا: {result.error}"
    if result.already_completed:
        return "قبلاً تأیید شده."

    user = await session.get(TelegramUser, payment.user_id)
    if user:
        if result.order_fulfilled and payment.order_id:
            from bot.db.models import Order

            order = await session.get(Order, payment.order_id)
            if order:
                await notify_order_fulfilled(
                    callback.bot,
                    session,
                    user,
                    order,
                    result.subscriptions,
                    header=f"✅ پرداخت کارت به کارت تأیید شد. سفارش #{order.id} فعال شد.",
                )
        elif result.wallet_credited:
            await notify_wallet_credited(
                callback.bot,
                user,
                payment.amount_toman,
                header=f"✅ پرداخت کارت به کارت تأیید شد. {format_toman(payment.amount_toman)} به کیف پول اضافه شد.",
            )

    logger.info("approved payment_id=%s admin=%s", payment_id, callback.from_user.id)
    session.add(
        AdminAuditLog(
            admin_telegram_id=callback.from_user.id,
            action="c2c_approve",
            details=f"payment_id={payment_id}",
        )
    )
    return "✅ تأیید و انجام شد."


async def build_payments_screen(session: AsyncSession) -> tuple[str, object]:
    pending = await session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(
            Payment.provider == PaymentProvider.C2C,
            Payment.status == PaymentStatus.PENDING_REVIEW,
        )
    )
    waiting = await session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(
            Payment.provider == PaymentProvider.C2C,
            Payment.status == PaymentStatus.PENDING,
        )
    )
    payments = (
        await session.scalars(
            select(Payment)
            .where(
                Payment.provider == PaymentProvider.C2C,
                Payment.status.in_(
                    [PaymentStatus.PENDING_REVIEW, PaymentStatus.PENDING]
                ),
            )
            .order_by(Payment.created_at.asc())
            .limit(15)
        )
    ).all()
    payments = sorted(
        list(payments),
        key=lambda p: (0 if p.status == PaymentStatus.PENDING_REVIEW else 1, p.created_at),
    )
    labels: dict[int, str] = {}
    for p in payments:
        user = await session.get(TelegramUser, p.user_id)
        age = format_relative_time(p.created_at)
        who = f"@{user.username}" if user and user.username else f"tg:{user.telegram_id if user else '?'}"
        labels[p.id] = f" {who} {p.amount_toman:,}ت {age}"
    text = (
        f"💳 <b>پرداخت‌های کارت به کارت</b>\n\n"
        f"در انتظار رسید: {waiting or 0}\n"
        f"در انتظار بررسی: {pending or 0}\n"
    )
    return text, c2c_payments_kb(list(payments), labels)


@router.callback_query(F.data == "admin:payments")
async def admin_payments_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    text, kb = await build_payments_screen(session)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:c2c:view:"))
async def admin_c2c_view(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    payment_id = int(callback.data.split(":")[-1])
    payment = await session.get(Payment, payment_id)
    if not payment:
        await callback.answer("یافت نشد.", show_alert=True)
        return
    user = await session.get(TelegramUser, payment.user_id)
    meta = parse_metadata(payment)
    who = f"@{user.username}" if user and user.username else f"tg:{user.telegram_id if user else '?'}"
    await callback.message.answer(
        f"Payment #{payment.id}\n"
        f"user: {who}\n"
        f"status: {payment.status.value}\n"
        f"amount: {format_toman(payment.amount_toman)}\n"
        f"age: {format_relative_time(payment.created_at)}\n"
        f"order_id: {payment.order_id}\n"
        f"metadata: {meta}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="« C2C", callback_data="admin:payments")],
            ]
        ),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:c2c:approve:"))
async def admin_c2c_approve(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return

    payment_id = int(callback.data.split(":")[-1])
    msg = await _approve_payment(callback, session, payment_id)
    try:
        if callback.message.caption:
            await callback.message.edit_caption(
                caption=f"{callback.message.caption}\n\n{msg}",
                reply_markup=None,
            )
        else:
            await callback.message.edit_text(f"{callback.message.text}\n\n{msg}")
    except Exception:
        await callback.message.answer(msg)
    await callback.answer(msg[:200], show_alert=len(msg) > 60)


@router.callback_query(F.data.startswith("admin:c2c:reject:"))
async def admin_c2c_reject_prompt(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return

    payment_id = int(callback.data.split(":")[-1])
    payment = await session.get(Payment, payment_id)
    if not payment:
        await callback.answer("پرداخت یافت نشد.", show_alert=True)
        return

    await state.set_state(AdminStates.c2c_reject_reason)
    await state.update_data(payment_id=payment_id, review_chat_id=callback.message.chat.id)
    await callback.answer()
    await callback.message.answer(
        f"دلیل رد پرداخت #{payment_id} را بنویسید (یا /skip برای رد بدون توضیح):",
        reply_markup=cancel_fsm_kb(),
    )


@router.message(AdminStates.c2c_reject_reason)
async def admin_c2c_reject_reason(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if not _is_admin(message.from_user.id):
        return

    data = await state.get_data()
    payment_id = data.get("payment_id")
    await state.clear()

    reason = "رد شده توسط ادمین"
    if message.text and message.text.strip() != "/skip":
        reason = message.text.strip()[:500]

    payment = await session.get(Payment, payment_id)
    if not payment:
        await message.answer("پرداخت یافت نشد.")
        return

    if payment.status in (PaymentStatus.COMPLETED, PaymentStatus.REJECTED):
        await message.answer("این پرداخت دیگر قابل رد نیست.")
        return

    payment.status = PaymentStatus.REJECTED
    update_metadata(payment, reject_reason=reason)
    await session.flush()

    user = await session.get(TelegramUser, payment.user_id)
    if user:
        try:
            await message.bot.send_message(
                user.telegram_id,
                f"❌ پرداخت کارت به کارت رد شد.\nدلیل: {reason}",
            )
        except Exception:
            pass

    logger.info("rejected payment_id=%s admin=%s", payment_id, message.from_user.id)
    session.add(
        AdminAuditLog(
            admin_telegram_id=message.from_user.id,
            action="c2c_reject",
            details=f"payment_id={payment_id} reason={reason[:100]}",
        )
    )
    snapshot = await build_ops_snapshot(session)
    await message.answer(f"❌ پرداخت #{payment_id} رد شد.", reply_markup=admin_menu_kb(snapshot))
