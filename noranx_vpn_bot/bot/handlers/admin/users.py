from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import AdminAuditLog, Subscription, SubscriptionStatus, TelegramUser
from bot.keyboards.common import cancel_fsm_kb
from bot.services.ip_limiter import IpLimiterService
from bot.services.marzban import MarzbanService
from bot.services.registry import get_sync_service
from bot.states import AdminStates
from bot.utils.formatting import format_toman
from bot.utils.telegram import safe_callback_answer

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


def user_card_kb(
    tg_id: int,
    username: str | None,
    *,
    dir_back: str | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📦 سرویس‌ها", callback_data=f"admin:user:subs:{tg_id}")],
        [InlineKeyboardButton(text="💰 کیف پول", callback_data=f"admin:wallet:user:{tg_id}")],
    ]
    if username:
        rows.append(
            [InlineKeyboardButton(text="🔄 Sync", callback_data=f"admin:user:sync:{username}")]
        )
    back_cb = dir_back or "admin:hub:users"
    rows.append([InlineKeyboardButton(text="« بازگشت", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_user_card(session: AsyncSession, user: TelegramUser) -> str:
    subs = (
        await session.scalars(select(Subscription).where(Subscription.user_id == user.id))
    ).all()
    active = sum(1 for s in subs if s.status == SubscriptionStatus.ACTIVE)
    banned = "بله" if getattr(user, "is_banned", False) else "خیر"
    uname = f"@{user.username}" if user.username else "—"
    return (
        f"<b>👤 کاربر</b>\n"
        f"تلگرام: <code>{user.telegram_id}</code> ({uname})\n"
        f"💰 موجودی: {format_toman(user.wallet_balance_toman)}\n"
        f"🎁 تست: {'بله' if user.trial_used else 'خیر'} | 🚫 مسدود: {banned}\n"
        f"📦 سرویس‌ها: {len(subs)} ({active} فعال)"
    )


@router.callback_query(F.data == "admin:users")
async def admin_users_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    from bot.keyboards.admin_hubs import users_hub_kb

    await state.clear()
    await callback.message.edit_text(
        "👥 <b>کاربران و پیام‌رسانی</b>",
        reply_markup=users_hub_kb(),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


async def show_user_card(
    message,
    session: AsyncSession,
    tg_id: int,
    *,
    edit: bool = False,
    dir_back: str | None = None,
) -> None:
    user = await session.scalar(select(TelegramUser).where(TelegramUser.telegram_id == tg_id))
    if not user:
        if edit:
            await message.edit_text("کاربر یافت نشد.")
        else:
            await message.answer("کاربر یافت نشد.")
        return
    text = await _render_user_card(session, user)
    sub = await session.scalar(
        select(Subscription).where(Subscription.user_id == user.id).limit(1)
    )
    username = sub.marzban_username if sub else None
    kb = user_card_kb(user.telegram_id, username, dir_back=dir_back)
    if edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(AdminStates.search_user)
async def admin_search_user(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    q = (message.text or "").strip()
    user = None
    if q.isdigit():
        user = await session.scalar(
            select(TelegramUser).where(TelegramUser.telegram_id == int(q))
        )
    elif q.startswith("@"):
        user = await session.scalar(
            select(TelegramUser).where(TelegramUser.username == q[1:])
        )
    else:
        sub = await session.scalar(
            select(Subscription).where(Subscription.marzban_username == q)
        )
        if sub:
            user = await session.get(TelegramUser, sub.user_id)
    if not user:
        await message.answer("کاربر یافت نشد.")
        return
    await show_user_card(message, session, user.telegram_id)


@router.callback_query(F.data.startswith("admin:user:subs:"))
async def admin_user_subs(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    tg_id = int(callback.data.split(":")[-1])
    user = await session.scalar(select(TelegramUser).where(TelegramUser.telegram_id == tg_id))
    if not user:
        await safe_callback_answer(callback, "یافت نشد.", show_alert=True)
        return
    subs = (
        await session.scalars(select(Subscription).where(Subscription.user_id == user.id))
    ).all()
    lines = [f"📦 سرویس‌های {tg_id}:"]
    for s in subs:
        lines.append(f"• {s.marzban_username} — {s.status.value}")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="« کارت کاربر", callback_data=f"admin:user:view:{tg_id}")]
        ]
    )
    await callback.message.edit_text(
        "\n".join(lines) if subs else "بدون سرویس.",
        reply_markup=kb,
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:user:sync:"))
async def admin_user_sync(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    username = callback.data.split(":", maxsplit=3)[-1]
    sub = await session.scalar(
        select(Subscription).where(Subscription.marzban_username == username)
    )
    if not sub:
        await safe_callback_answer(callback, "اشتراک در DB یافت نشد.", show_alert=True)
        return
    sync = get_sync_service()
    await sync.sync_subscription(session, sub)
    ok = await sync.sync_limiters_for_subscription(sub)
    await session.commit()
    await safe_callback_answer(
        callback,
        f"Sync {username}: {sub.status.value} | limiters={'OK' if ok else 'FAIL'}",
        show_alert=True,
    )


@router.message(Command("sync_user"))
async def sync_user_cmd(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("استفاده: /sync_user username", parse_mode=None)
        return
    username = parts[1].strip()
    sub = await session.scalar(
        select(Subscription).where(Subscription.marzban_username == username)
    )
    if not sub:
        await message.answer("اشتراک در دیتابیس یافت نشد.")
        return
    sync = get_sync_service()
    await sync.sync_subscription(session, sub)
    ok = await sync.sync_limiters_for_subscription(sub)
    await message.answer(
        f"Sync {username}: status={sub.status.value}, limiters={'OK' if ok else 'FAIL'}"
    )


@router.message(Command("re_enable"))
async def re_enable_cmd(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("استفاده: /re_enable username", parse_mode=None)
        return
    username = parts[1].strip()
    sub = await session.scalar(
        select(Subscription).where(Subscription.marzban_username == username)
    )
    if not sub:
        await message.answer("یافت نشد.")
        return
    from bot.services.provisioner import ProvisionerService

    s = get_settings()
    p = ProvisionerService(s, MarzbanService(s), IpLimiterService(s))
    ok = await p.re_enable(sub)
    if ok:
        sub.status = SubscriptionStatus.ACTIVE
        await session.flush()
    await message.answer("فعال شد." if ok else "خطا در فعال‌سازی.")


@router.message(Command("user"))
async def lookup_user_cmd(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("استفاده: /user <telegram_id>")
        return
    await show_user_card(message, session, int(parts[1].strip()))
