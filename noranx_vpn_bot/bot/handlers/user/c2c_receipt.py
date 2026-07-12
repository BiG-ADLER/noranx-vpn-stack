import hashlib
import io

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import C2CReceiptDedup, Payment, PaymentProvider, PaymentStatus, TelegramUser
from bot.services.payment.c2c_review import (
    find_duplicate_ocr_ref,
    post_to_review_channel,
)
from bot.services.payment.c2c_utils import now_iso, parse_metadata, update_metadata
from bot.services.payment.receipt_ocr import extract_receipt_hints
from bot.states import PaymentStates
from bot.utils.logging import get_logger

logger = get_logger("c2c")

router = Router()


async def _download_photo_sha256(bot: Bot, file_id: str) -> tuple[bytes, str]:
    file = await bot.get_file(file_id)
    buf = io.BytesIO()
    await bot.download_file(file.file_path, buf)
    data = buf.getvalue()
    return data, hashlib.sha256(data).hexdigest()


@router.message(PaymentStates.waiting_c2c_receipt, F.photo)
async def c2c_receipt_photo(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    settings = get_settings()
    data = await state.get_data()
    payment_id = data.get("payment_id")
    if not payment_id:
        await state.clear()
        await message.answer("جلسه پرداخت منقضی شد. دوباره تلاش کنید.")
        return

    payment = await session.get(Payment, payment_id)
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == message.from_user.id)
    )
    if not payment or not user or payment.user_id != user.id:
        await state.clear()
        await message.answer("پرداخت یافت نشد.")
        return

    if user.is_banned:
        await message.answer("حساب شما مسدود است.")
        return

    if payment.status != PaymentStatus.PENDING:
        await state.clear()
        if payment.status == PaymentStatus.PENDING_REVIEW:
            await message.answer("رسید شما قبلاً ثبت شده و در حال بررسی است.")
        else:
            await message.answer("این پرداخت دیگر قابل ثبت رسید نیست.")
        return

    photo = message.photo[-1]
    try:
        image_bytes, sha256 = await _download_photo_sha256(bot, photo.file_id)
    except Exception:
        logger.exception("receipt download failed payment_id=%s", payment_id)
        await message.answer("خطا در دریافت تصویر. دوباره بفرستید.")
        return

    existing_dedup = await session.scalar(
        select(C2CReceiptDedup).where(C2CReceiptDedup.receipt_sha256 == sha256)
    )
    if existing_dedup:
        logger.info("dedup_hit payment_id=%s sha=%s", payment_id, sha256[:12])
        await message.answer("این رسید قبلاً ثبت شده است.")
        return

    ocr = await extract_receipt_hints(image_bytes, enabled=settings.c2c_ocr_enabled)
    amount_mismatch = bool(
        ocr.amount is not None and ocr.amount != payment.amount_toman
    )
    duplicate_ref = False
    if ocr.ref:
        dup = await find_duplicate_ocr_ref(session, ocr.ref, payment.id)
        duplicate_ref = dup is not None

    session.add(C2CReceiptDedup(receipt_sha256=sha256, payment_id=payment.id))
    update_metadata(
        payment,
        receipt_file_id=photo.file_id,
        receipt_sha256=sha256,
        receipt_uploaded_at=now_iso(),
        ocr={
            "amount": ocr.amount,
            "ref": ocr.ref,
            "confidence": ocr.confidence,
        },
    )
    payment.status = PaymentStatus.PENDING_REVIEW
    await session.flush()

    review_msg_id = await post_to_review_channel(
        bot,
        settings,
        session,
        payment,
        user,
        photo.file_id,
        ocr,
        amount_mismatch=amount_mismatch,
        duplicate_ref=duplicate_ref,
    )
    if review_msg_id:
        update_metadata(payment, review_message_id=review_msg_id)

    await state.clear()
    logger.info(
        "receipt_uploaded payment_id=%s user_id=%s ref=%s",
        payment.id,
        user.id,
        parse_metadata(payment).get("payment_ref"),
    )
    await message.answer(
        "✅ رسید دریافت شد.\n"
        f"وضعیت: در انتظار بررسی\n"
        f"شماره پیگیری: #{payment.id}\n"
        f"زمان تقریبی: زیر ۳۰ دقیقه"
    )


@router.callback_query(F.data.startswith("c2c:cancel:"))
async def c2c_cancel(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    payment_id = int(callback.data.split(":")[-1])
    payment = await session.get(Payment, payment_id)
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not payment or not user or payment.user_id != user.id:
        await callback.answer("پرداخت نامعتبر.", show_alert=True)
        return

    if payment.status == PaymentStatus.PENDING:
        payment.status = PaymentStatus.FAILED
        update_metadata(payment, reject_reason="لغو توسط کاربر")
        await session.flush()

    await state.clear()
    await callback.message.edit_text("❌ پرداخت کارت به کارت لغو شد.")
    await callback.answer()
