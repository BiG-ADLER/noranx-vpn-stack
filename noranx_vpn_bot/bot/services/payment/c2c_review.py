from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db.models import Order, Payment, PaymentProvider, RechargePackage, TelegramUser
from bot.services.payment.c2c_utils import parse_metadata
from bot.services.payment.receipt_ocr import OcrHints
from bot.utils.formatting import format_toman
from bot.utils.logging import get_logger

logger = get_logger("c2c")


def review_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید",
                    callback_data=f"admin:c2c:approve:{payment_id}",
                ),
                InlineKeyboardButton(
                    text="❌ رد",
                    callback_data=f"admin:c2c:reject:{payment_id}",
                ),
            ],
        ]
    )


def cancel_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ لغو پرداخت",
                    callback_data=f"c2c:cancel:{payment_id}",
                ),
            ],
        ]
    )


async def find_duplicate_ocr_ref(
    session: AsyncSession, ref: str, exclude_payment_id: int
) -> Payment | None:
    if not ref:
        return None
    payments = (
        await session.scalars(
            select(Payment).where(
                Payment.provider == PaymentProvider.C2C,
                Payment.id != exclude_payment_id,
            )
        )
    ).all()
    for p in payments:
        meta = parse_metadata(p)
        ocr = meta.get("ocr") or {}
        if isinstance(ocr, dict) and ocr.get("ref") == ref:
            return p
    return None


def build_review_caption(
    payment: Payment,
    user: TelegramUser,
    *,
    ocr: OcrHints | None = None,
    amount_mismatch: bool = False,
    duplicate_ref: bool = False,
) -> str:
    meta = parse_metadata(payment)
    ref = meta.get("payment_ref", payment.external_id)
    username = f"@{user.username}" if user.username else "—"
    lines = []
    if amount_mismatch:
        lines.append("⚠️ مبلغ OCR با مبلغ مورد انتظار مطابقت ندارد")
    if duplicate_ref:
        lines.append("⚠️ شماره پیگیری OCR قبلاً استفاده شده")

    if payment.order_id:
        ptype = f"سفارش #{payment.order_id}"
    elif payment.recharge_package_id:
        ptype = f"شارژ کیف پول +{format_toman(payment.amount_toman)}"
    else:
        ptype = "نامشخص"

    lines.extend(
        [
            f"C2C #{payment.id} | ref {ref}",
            f"User: {username} (tg {user.telegram_id})",
            f"Type: {ptype}",
            f"Expected: {format_toman(payment.amount_toman)}",
        ]
    )
    if ocr and (ocr.amount or ocr.ref):
        ocr_amount = str(ocr.amount) if ocr.amount else "—"
        ocr_ref = ocr.ref or "—"
        lines.append(f"OCR hint: amount={ocr_amount} ref={ocr_ref} (conf {ocr.confidence:.1f})")
    return "\n".join(lines)


async def post_to_review_channel(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    payment: Payment,
    user: TelegramUser,
    photo_file_id: str,
    ocr: OcrHints,
    *,
    amount_mismatch: bool = False,
    duplicate_ref: bool = False,
) -> int | None:
    channel_id = settings.c2c_review_channel_id
    if not channel_id:
        logger.warning("C2C_REVIEW_CHANNEL_ID not set payment_id=%s", payment.id)
        return None

    caption = build_review_caption(
        payment,
        user,
        ocr=ocr,
        amount_mismatch=amount_mismatch,
        duplicate_ref=duplicate_ref,
    )
    try:
        msg = await bot.send_photo(
            channel_id,
            photo_file_id,
            caption=caption,
            reply_markup=review_keyboard(payment.id),
        )
        return msg.message_id
    except Exception as e:
        logger.exception("review channel post failed payment_id=%s: %s", payment.id, e)
        return None


async def payment_context_line(session: AsyncSession, payment: Payment) -> str:
    if payment.order_id:
        order = await session.get(Order, payment.order_id)
        if order:
            return f"سفارش #{order.id} — {format_toman(payment.amount_toman)}"
    if payment.recharge_package_id:
        pkg = await session.get(RechargePackage, payment.recharge_package_id)
        if pkg:
            return f"شارژ {format_toman(pkg.amount_toman)}"
    return format_toman(payment.amount_toman)
