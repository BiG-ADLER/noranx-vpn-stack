import json

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import Payment, PaymentProvider, PaymentStatus, RechargePackage, TelegramUser
from bot.keyboards.common import cancel_fsm_kb
from bot.keyboards.user import (
    CHECKOUT_CRYPTO_HINT,
    crypto_confirm_kb,
    recharge_menu_kb,
    recharge_packages_kb,
    wallet_kb,
)
from bot.services.exchange_rate import ExchangeRateError, ExchangeRateService
from bot.services.payment.c2c_base import get_c2c_adapter
from bot.services.payment.c2c_review import cancel_keyboard
from bot.services.payment.c2c_utils import build_c2c_metadata, c2c_available
from bot.services.payment.nowpayments import NowPaymentsError, NowPaymentsService
from bot.services.payment.wallet import WalletService
from bot.states import PaymentStates, WalletStates
from bot.utils.formatting import format_irr, format_toman, format_usd_irr_line, usd_to_toman

router = Router()
wallet_service = WalletService()
fx_service = ExchangeRateService()


async def _rate_banner(session: AsyncSession) -> str:
    try:
        rate = await fx_service.get_rate(session)
        return format_usd_irr_line(rate.irr_per_usd)
    except ExchangeRateError:
        return "نرخ لحظه‌ای: در دسترس نیست"


@router.callback_query(F.data == "menu:wallet")
async def wallet_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    balance = await wallet_service.get_balance(session, user.id) if user else 0
    rate_line = await _rate_banner(session)
    await callback.message.edit_text(
        f"💰 کیف پول\n"
        f"موجودی: {format_toman(balance)}\n\n"
        f"{rate_line}\n\n"
        f"{CHECKOUT_CRYPTO_HINT}",
        reply_markup=wallet_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "wallet:recharge")
async def wallet_recharge(callback: CallbackQuery, session: AsyncSession) -> None:
    rate_line = await _rate_banner(session)
    settings = get_settings()
    min_usd = settings.fx_min_usd_recharge
    try:
        rate = await fx_service.get_rate(session)
        min_irr = fx_service.usd_to_irr(min_usd, rate)
        min_line = f"حداقل شارژ کریپتو: {min_usd:g}$ ≈ {format_irr(min_irr)}"
    except ExchangeRateError:
        min_line = f"حداقل شارژ کریپتو: {min_usd:g}$"

    await callback.message.edit_text(
        f"➕ شارژ کیف پول\n\n{rate_line}\n{min_line}",
        reply_markup=recharge_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "wallet:c2c:packages")
async def wallet_c2c_packages(callback: CallbackQuery, session: AsyncSession) -> None:
    packages = (
        await session.scalars(
            select(RechargePackage)
            .where(RechargePackage.is_active)
            .order_by(RechargePackage.sort_order)
        )
    ).all()
    if not packages:
        await callback.answer("بسته شارژ تعریف نشده.", show_alert=True)
        return
    await callback.message.edit_text(
        "💳 کارت به کارت — مبلغ را انتخاب کنید:",
        reply_markup=recharge_packages_kb(list(packages)),
    )
    await callback.answer()


@router.callback_query(F.data == "wallet:crypto:custom")
async def wallet_crypto_custom(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    settings = get_settings()
    np = NowPaymentsService(settings)
    if not np.enabled:
        await callback.answer("پرداخت کریپتو فعال نیست.", show_alert=True)
        return
    try:
        rate = await fx_service.get_rate(session)
    except ExchangeRateError:
        await callback.answer("نرخ دلار در دسترس نیست.", show_alert=True)
        return

    await state.set_state(WalletStates.waiting_crypto_usd_amount)
    min_usd = settings.fx_min_usd_recharge
    await callback.message.answer(
        f"{format_usd_irr_line(rate.irr_per_usd)}\n\n"
        f"مبلغ را به **دلار** وارد کنید (حداقل {min_usd:g}):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_fsm_kb(),
    )
    await callback.answer()


@router.message(WalletStates.waiting_crypto_usd_amount)
async def wallet_crypto_amount(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    settings = get_settings()
    text = (message.text or "").strip().replace(",", ".").replace("٬", ".")
    try:
        amount_usd = float(text)
    except ValueError:
        await message.answer("عدد نامعتبر. مثال: 5 یا 10.5")
        return

    min_usd = settings.fx_min_usd_recharge
    if amount_usd < min_usd:
        await message.answer(f"حداقل مبلغ شارژ {min_usd:g}$ است.")
        return

    try:
        rate = await fx_service.get_rate(session)
    except ExchangeRateError as e:
        await message.answer(str(e))
        return

    toman = usd_to_toman(amount_usd, rate.irr_per_usd)
    irr_total = fx_service.usd_to_irr(amount_usd, rate)

    await state.update_data(
        amount_usd=amount_usd,
        toman=toman,
        irr_total=irr_total,
        irr_per_usd=rate.irr_per_usd,
        rate_source=rate.source,
    )

    await message.answer(
        f"📋 تأیید شارژ\n\n"
        f"مبلغ: {amount_usd:g}$\n"
        f"معادل: {format_irr(irr_total)} ({format_toman(toman)})\n"
        f"نرخ: {format_usd_irr_line(rate.irr_per_usd)}\n\n"
        f"تأیید می‌کنید؟",
        reply_markup=crypto_confirm_kb(),
    )


@router.callback_query(F.data == "wallet:crypto:confirm")
async def wallet_crypto_confirm(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    amount_usd = data.get("amount_usd")
    toman = data.get("toman")
    if not amount_usd or not toman:
        await callback.answer("جلسه منقضی شد.", show_alert=True)
        await state.clear()
        return

    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not user:
        await callback.answer("خطا.", show_alert=True)
        return

    settings = get_settings()
    np = NowPaymentsService(settings)
    ipn_url = f"{settings.public_webhook_base_url.rstrip('/')}/webhooks/nowpayments"
    order_ref = f"WALLET-{user.id}-{int(amount_usd * 100)}"

    try:
        invoice = await np.create_payment_usd(
            float(amount_usd),
            order_ref,
            "Wallet recharge",
            ipn_url,
            min_usd=settings.fx_min_usd_recharge,
        )
    except NowPaymentsError as e:
        await callback.answer("خطا در ایجاد پرداخت.", show_alert=True)
        await callback.message.answer(f"❌ {e}")
        return

    meta = {
        "type": "wallet_recharge",
        "user_id": user.id,
        "usd": amount_usd,
        "irr_per_usd": data.get("irr_per_usd"),
        "irr_total": data.get("irr_total"),
        "rate_source": data.get("rate_source"),
        "toman_credited": toman,
    }
    session.add(
        Payment(
            user_id=user.id,
            provider=PaymentProvider.NOWPAYMENTS,
            external_id=invoice.payment_id,
            amount_toman=toman,
            status=PaymentStatus.PENDING,
            metadata_json=json.dumps(meta, ensure_ascii=False),
        )
    )
    await session.flush()
    await state.clear()

    await callback.message.answer(
        f"لینک پرداخت ({amount_usd:g}$ ≈ {format_toman(toman)}):\n{invoice.pay_url}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wallet:pkg:"))
async def wallet_pkg(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    pkg_id = int(callback.data.split(":")[-1])
    pkg = await session.get(RechargePackage, pkg_id)
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not pkg or not user:
        await callback.answer("خطا.", show_alert=True)
        return

    settings = get_settings()
    if not c2c_available(settings):
        await callback.answer("پرداخت کارت به کارت فعال نیست.", show_alert=True)
        return

    c2c = get_c2c_adapter(settings)
    intent = await c2c.create_recharge(user.id, pkg.id, pkg.amount_toman)
    payment = Payment(
        user_id=user.id,
        recharge_package_id=pkg.id,
        provider=PaymentProvider.C2C,
        external_id=intent.external_id,
        amount_toman=pkg.amount_toman,
        status=PaymentStatus.PENDING,
        metadata_json=build_c2c_metadata(
            intent.external_id, pkg.amount_toman, package_id=pkg.id
        ),
    )
    session.add(payment)
    await session.flush()

    await state.set_state(PaymentStates.waiting_c2c_receipt)
    await state.update_data(payment_id=payment.id)

    await callback.message.answer(
        f"💳 شارژ {format_toman(pkg.amount_toman)}\n\n{intent.instructions}",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(payment.id),
    )
    await callback.answer()
