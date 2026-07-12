import re
import time
from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import AdminAuditLog, Subscription, SubscriptionStatus, TelegramUser, TrafficAnomalyEvent
from bot.handlers.admin.users import _is_admin
from bot.keyboards.admin_marzban import marzban_list_kb, marzban_user_kb, marzban_user_row_kb
from bot.services.ip_limiter import IpLimiterService
from bot.services.marzban import MarzbanService
from bot.services.sync import SyncService
from bot.services.registry import get_marzban, get_sync_service
from bot.services.traffic_anomaly import TrafficAnomalyService
from bot.states import AdminStates
from bot.utils.formatting import format_bytes, format_expiry
from bot.keyboards.common import cancel_fsm_kb
from bot.utils.logging import get_logger
from bot.utils.telegram import safe_callback_answer

logger = get_logger("marzban_admin")

router = Router()
PAGE_SIZE = 10


def _services() -> tuple[MarzbanService, SyncService]:
    return get_marzban(), get_sync_service()


async def _audit(session: AsyncSession, admin_id: int, action: str, details: str) -> None:
    session.add(
        AdminAuditLog(
            admin_telegram_id=admin_id,
            action=action,
            details=details[:2000],
        )
    )


async def _remove_limiters(username: str) -> None:
    s = get_settings()
    ip_lim = IpLimiterService(s)
    await ip_lim.remove_limit(username)


async def _sync_limiters_for_username(session: AsyncSession, username: str) -> None:
    sub = await session.scalar(
        select(Subscription).where(Subscription.marzban_username == username)
    )
    if not sub:
        return
    _, sync = _services()
    await sync.sync_limiters_for_subscription(sub)


def _anomaly_service() -> TrafficAnomalyService:
    return TrafficAnomalyService(get_settings(), get_marzban())


@router.callback_query(F.data.startswith("admin:marzban:list:"))
async def marzban_list(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    page = int(callback.data.split(":")[-1])
    marzban, _ = _services()
    users, total = await marzban.list_users(offset=page * PAGE_SIZE, limit=PAGE_SIZE)
    lines = [f"🖥 Marzban users ({total} total)\n"]
    rows = []
    for u in users:
        exp = format_expiry(
            datetime.fromtimestamp(u.expire, tz=UTC) if u.expire else None
        )
        lines.append(
            f"• {u.username} | {u.status} | {format_bytes(u.used_traffic)} | exp {exp}"
        )
        rows.extend(marzban_user_row_kb(u.username).inline_keyboard)
    kb = marzban_list_kb(page, total, PAGE_SIZE)
    rows.extend(kb.inline_keyboard)
    from aiogram.types import InlineKeyboardMarkup

    await callback.message.edit_text(
        "\n".join(lines[:40]) if lines else "هیچ کاربری یافت نشد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:marzban:view:"))
async def marzban_view(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    username = callback.data.split(":", maxsplit=3)[-1]
    marzban, _ = _services()
    u = await marzban.get_user(username)
    if not u:
        await callback.answer("کاربر یافت نشد.", show_alert=True)
        return
    sub = await session.scalar(
        select(Subscription).where(Subscription.marzban_username == username)
    )
    exp = format_expiry(datetime.fromtimestamp(u.expire, tz=UTC) if u.expire else None)
    limit_str = format_bytes(u.data_limit) if u.data_limit else "نامحدود"
    text = (
        f"👤 {u.username}\n"
        f"Status: {u.status}\n"
        f"Traffic: {format_bytes(u.used_traffic)} / {limit_str}\n"
        f"Expire: {exp}\n"
        f"Note: {u.note or '—'}\n"
        f"Bot DB: {'linked #' + str(sub.id) if sub else 'not linked'}"
    )
    await callback.message.edit_text(text, reply_markup=marzban_user_kb(username))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:marzban:enable:"))
async def marzban_enable(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    username = callback.data.split(":", maxsplit=3)[-1]
    marzban, _ = _services()
    await marzban.modify_user(username, status="active")
    await _sync_limiters_for_username(session, username)
    await _audit(session, callback.from_user.id, "marzban_enable", username)
    await callback.answer("فعال شد.")


@router.callback_query(F.data.startswith("admin:marzban:disable:"))
async def marzban_disable(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    username = callback.data.split(":", maxsplit=3)[-1]
    marzban, _ = _services()
    await marzban.modify_user(username, status="disabled")
    await _remove_limiters(username)
    await _audit(session, callback.from_user.id, "marzban_disable", username)
    await callback.answer("غیرفعال شد.")


@router.callback_query(F.data.startswith("admin:marzban:extend:"))
async def marzban_extend_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return
    username = callback.data.split(":", maxsplit=3)[-1]
    await state.set_state(AdminStates.marzban_extend_days)
    await state.update_data(marzban_username=username)
    await callback.answer()
    await callback.message.answer(f"چند روز به {username} اضافه شود؟", reply_markup=cancel_fsm_kb())


@router.message(AdminStates.marzban_extend_days)
async def marzban_extend_days(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    username = data.get("marzban_username")
    await state.clear()
    try:
        days = int((message.text or "").strip())
    except ValueError:
        await message.answer("عدد نامعتبر.")
        return
    marzban, _ = _services()
    u = await marzban.get_user(username)
    if not u:
        await message.answer("کاربر یافت نشد.")
        return
    base = u.expire if u.expire and u.expire > time.time() else time.time()
    new_expire = int(base + days * 86400)
    await marzban.modify_user(username, expire=new_expire)
    await _audit(session, message.from_user.id, "marzban_extend", f"{username}+{days}d")
    await message.answer(f"✅ {username} تا {format_expiry(datetime.fromtimestamp(new_expire, tz=UTC))}")


@router.callback_query(F.data.startswith("admin:marzban:reset:"))
async def marzban_reset(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    username = callback.data.split(":", maxsplit=3)[-1]
    marzban, _ = _services()
    await marzban.reset_user_traffic(username)
    await _audit(session, callback.from_user.id, "marzban_reset_traffic", username)
    await callback.answer("ترافیک ریست شد.")


@router.callback_query(F.data.startswith("admin:marzban:sync:"))
async def marzban_sync(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    username = callback.data.split(":", maxsplit=3)[-1]
    sub = await session.scalar(
        select(Subscription).where(Subscription.marzban_username == username)
    )
    if not sub:
        await callback.answer("در DB یافت نشد — Import کنید.", show_alert=True)
        return
    _, sync = _services()
    await sync.sync_subscription(session, sub)
    await callback.answer(f"Sync OK: {sub.status.value}")


@router.callback_query(F.data.startswith("admin:marzban:import:"))
async def marzban_import(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    username = callback.data.split(":", maxsplit=3)[-1]
    existing = await session.scalar(
        select(Subscription).where(Subscription.marzban_username == username)
    )
    if existing:
        await callback.answer("قبلاً در DB است.", show_alert=True)
        return
    marzban, sync = _services()
    mb = await marzban.get_user(username)
    if not mb:
        await callback.answer("در Marzban یافت نشد.", show_alert=True)
        return
    tg_match = re.search(r"tg:(\d+)", mb.note or "")
    user = None
    if tg_match:
        user = await session.scalar(
            select(TelegramUser).where(TelegramUser.telegram_id == int(tg_match.group(1)))
        )
    if not user:
        await callback.answer(
            "کاربر تلگرام از note پیدا نشد (tg:ID). ابتدا note را در Marzban تنظیم کنید.",
            show_alert=True,
        )
        return
    sub = Subscription(
        user_id=user.id,
        marzban_username=username,
        subscription_url=mb.subscription_url,
        device_limit=1,
        ip_limit=1,
        status=SubscriptionStatus.ACTIVE,
        data_limit_bytes=mb.data_limit or None,
        expires_at=datetime.fromtimestamp(mb.expire, tz=UTC) if mb.expire else None,
    )
    session.add(sub)
    await session.flush()
    await sync.sync_limiters_for_subscription(sub)
    await _audit(session, callback.from_user.id, "marzban_import", username)
    await callback.answer(f"Import #{sub.id} — assign user manually if needed.")


@router.callback_query(F.data.startswith("admin:marzban:delete:"))
async def marzban_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    username = callback.data.split(":", maxsplit=3)[-1]
    marzban, _ = _services()
    await _remove_limiters(username)
    await marzban.delete_user(username)
    sub = await session.scalar(
        select(Subscription).where(Subscription.marzban_username == username)
    )
    if sub:
        sub.status = SubscriptionStatus.DISABLED
    await _audit(session, callback.from_user.id, "marzban_delete", username)
    await callback.answer("حذف شد.")
    await callback.message.edit_text(f"🗑 {username} deleted from Marzban.")


@router.callback_query(F.data.startswith("admin:anomaly:reenable:"))
async def anomaly_reenable_prompt(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    event_id = int(callback.data.split(":")[-1])
    event = await session.get(TrafficAnomalyEvent, event_id)
    if not event:
        await callback.answer("رویداد یافت نشد.", show_alert=True)
        return
    await state.set_state(AdminStates.anomaly_reenable_note)
    await state.update_data(anomaly_event_id=event_id)
    await callback.answer()
    await callback.message.answer(
        f"یادداشت بررسی برای re-enable کاربر {event.marzban_username} را ارسال کنید:",
        reply_markup=cancel_fsm_kb(),
    )


@router.message(AdminStates.anomaly_reenable_note)
async def anomaly_reenable_apply(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    event_id = int(data.get("anomaly_event_id") or 0)
    note = (message.text or "").strip()
    if not event_id or len(note) < 8:
        await message.answer("یادداشت بررسی نامعتبر است (حداقل ۸ کاراکتر).")
        return
    service = _anomaly_service()
    event = await service.reenable_with_note(session, event_id, note, message.from_user.id)
    if not event:
        await message.answer("رویداد یافت نشد.")
        return
    await message.answer(f"✅ {event.marzban_username} دوباره فعال شد و یادداشت ثبت گردید.")


@router.callback_query(F.data == "admin:marzban:drift")
async def marzban_drift(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    marzban, sync = _services()
    drift = await sync.count_limiter_drift(session)
    bot_subs = (
        await session.scalars(select(Subscription.marzban_username))
    ).all()
    mb_users, total = await marzban.list_users(limit=500)
    mb_names = {u.username for u in mb_users}
    bot_names = set(bot_subs)
    orphan_mb = mb_names - bot_names
    orphan_bot = bot_names - mb_names
    text = (
        f"Drift report\n"
        f"Limiter drift: {drift}\n"
        f"Marzban-only (sample): {len(orphan_mb)}\n"
        f"Bot-only (sample): {len(orphan_bot)}\n"
    )
    if orphan_mb:
        text += "MB only: " + ", ".join(list(orphan_mb)[:5]) + "\n"
    if orphan_bot:
        text += "Bot only: " + ", ".join(list(orphan_bot)[:5])
    await callback.message.answer(text, parse_mode=None)
    await callback.answer()
