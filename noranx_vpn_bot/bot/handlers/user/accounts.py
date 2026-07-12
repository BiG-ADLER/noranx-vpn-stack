from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import Plan, Subscription, TelegramUser
from bot.keyboards.user import account_detail_kb, checkout_kb, subscriptions_kb
from bot.services.ip_limiter import IpLimiterService
from bot.services.marzban import MarzbanService
from bot.services.orders import OrderService
from bot.services.discount import DiscountService
from bot.services.payment.wallet import WalletService
from bot.services.provisioner import ProvisionerService
from bot.services.referral import ReferralService
from bot.services.registry import get_sync_service
from bot.utils.formatting import (
    days_until_expiry,
    format_bytes,
    format_expiry,
    format_toman,
    format_traffic_usage,
    traffic_progress_bar,
)
from bot.utils.qr import make_qr_png_bytes

router = Router()


def _order_service() -> OrderService:
    s = get_settings()
    return OrderService(
        WalletService(),
        DiscountService(),
        ProvisionerService(s, MarzbanService(s), IpLimiterService(s)),
        ReferralService(s),
    )


@router.callback_query(F.data == "menu:accounts")
async def list_accounts(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not user:
        await callback.answer("ابتدا /start بزنید.", show_alert=True)
        return
    subs = (
        await session.scalars(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.created_at.desc())
        )
    ).all()
    if not subs:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🛒 خرید جدید", callback_data="menu:shop")],
                [
                    InlineKeyboardButton(text="📖 راهنما", callback_data="menu:guide"),
                    InlineKeyboardButton(text="« منو", callback_data="menu:main"),
                ],
            ]
        )
        await callback.message.edit_text(
            "شما هنوز سرویسی ندارید.",
            reply_markup=kb,
        )
    else:
        await callback.message.edit_text(
            f"📦 سرویس‌های شما ({len(subs)}):",
            reply_markup=subscriptions_kb(list(subs)),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("acc:view:"))
async def view_account(callback: CallbackQuery, session: AsyncSession) -> None:
    sub_id = int(callback.data.split(":")[-1])
    sub = await session.get(Subscription, sub_id)
    if not sub:
        await callback.answer("یافت نشد.", show_alert=True)
        return
    sync = get_sync_service()
    await sync.sync_subscription(session, sub)
    status_icon = "🟢" if sub.status.value == "active" else "🔴"
    days = days_until_expiry(sub.expires_at)
    days_line = f" ({days} روز مانده)" if days is not None else ""
    traffic_line = format_traffic_usage(sub.used_traffic_bytes, sub.data_limit_bytes)
    if sub.data_limit_bytes and sub.data_limit_bytes > 0:
        traffic_line += f"\n{traffic_progress_bar(sub.used_traffic_bytes, sub.data_limit_bytes)}"
    from bot.utils.subscription_url import normalize_subscription_url

    sub_url = normalize_subscription_url(sub.subscription_url) if sub.subscription_url else ""
    url_block = f"\n🔗 لینک اشتراک:\n<code>{sub_url}</code>" if sub_url else ""
    text = (
        f"📦 <b>{sub.label or sub.marzban_username}</b> — {status_icon} {sub.status.value}\n"
        f"⏳ انقضا: {format_expiry(sub.expires_at)}{days_line}\n"
        f"📊 ترافیک: {traffic_line}\n"
        f"📱 ظرفیت: {sub.device_limit} دستگاه / IP"
        f"{url_block}"
    )
    await callback.message.edit_text(
        text, reply_markup=account_detail_kb(sub.id, sub.plan_id), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("acc:refresh:"))
async def account_refresh(callback: CallbackQuery, session: AsyncSession) -> None:
    sub_id = int(callback.data.split(":")[-1])
    sub = await session.get(Subscription, sub_id)
    if not sub:
        await callback.answer("یافت نشد.", show_alert=True)
        return
    sync = get_sync_service()
    await sync.sync_subscription(session, sub)
    await sync.sync_limiters_for_subscription(sub)
    await callback.answer("بروزرسانی شد — لینک ارسال می‌شود.")
    await send_subscription_details(
        callback.bot,
        callback.from_user.id,
        marzban_username=sub.marzban_username,
        subscription_url=sub.subscription_url,
        device_limit=sub.device_limit,
        header="🔄 اشتراک بروزرسانی شد:",
    )


@router.callback_query(F.data.startswith("acc:link:"))
async def account_link(callback: CallbackQuery, session: AsyncSession) -> None:
    sub_id = int(callback.data.split(":")[-1])
    sub = await session.get(Subscription, sub_id)
    from bot.utils.subscription_url import normalize_subscription_url

    if sub and sub.subscription_url:
        await callback.message.answer(f"🔗 {normalize_subscription_url(sub.subscription_url)}")
    await callback.answer()


@router.callback_query(F.data.startswith("acc:qr:"))
async def account_qr(callback: CallbackQuery, session: AsyncSession) -> None:
    sub_id = int(callback.data.split(":")[-1])
    sub = await session.get(Subscription, sub_id)
    from bot.utils.subscription_url import normalize_subscription_url

    if sub and sub.subscription_url:
        qr = make_qr_png_bytes(normalize_subscription_url(sub.subscription_url))
        await callback.message.answer_photo(
            BufferedInputFile(qr, filename="qr.png"), caption="QR اشتراک"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("acc:usage:"))
async def account_usage(callback: CallbackQuery, session: AsyncSession) -> None:
    sub_id = int(callback.data.split(":")[-1])
    sub = await session.get(Subscription, sub_id)
    if not sub:
        await callback.answer("یافت نشد.", show_alert=True)
        return
    s = get_settings()
    mb = await MarzbanService(s).get_user(sub.marzban_username)
    if mb:
        sub.used_traffic_bytes = mb.used_traffic
        await session.flush()
    await callback.message.answer(
        f"📊 مصرف: {format_bytes(sub.used_traffic_bytes)} / نامحدود"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("renew:start:"))
async def renew_start(callback: CallbackQuery, session: AsyncSession) -> None:
    sub_id = int(callback.data.split(":")[-1])
    sub = await session.get(Subscription, sub_id)
    if not sub or not sub.plan_id:
        await callback.answer("تمدید این حساب ممکن نیست.", show_alert=True)
        return
    plan = await session.get(Plan, sub.plan_id)
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    svc = _order_service()
    order = await svc.create_order(
        session,
        user.id,
        plan,
        1,
        is_renewal=True,
        renew_subscription_id=sub.id,
    )
    await callback.message.answer(
        f"🔄 تمدید {plan.name_fa}\nمبلغ: {format_toman(order.total_toman)}",
        reply_markup=checkout_kb(order.id),
    )
    await callback.answer()
