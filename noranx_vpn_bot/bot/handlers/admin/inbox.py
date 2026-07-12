from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from bot.config import get_settings
from bot.db.models import AdminAuditLog, Subscription, SubscriptionStatus
from bot.handlers.admin.users import _is_admin
from bot.keyboards.admin_inbox import inbox_kb
from bot.services.admin_ops import build_ops_snapshot, format_ops_inbox_text
from bot.services.registry import get_sync_service
from bot.utils.telegram import safe_callback_answer

router = Router()


@router.callback_query(F.data == "admin:inbox")
async def admin_inbox(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    snapshot = await build_ops_snapshot(session)
    text = format_ops_inbox_text(snapshot)
    recent = (
        await session.scalars(
            select(AdminAuditLog).order_by(AdminAuditLog.id.desc()).limit(5)
        )
    ).all()
    if recent:
        text += "\n\n<b>آخرین اقدامات ادمین</b>"
        for row in recent:
            text += f"\n• {row.action}: {(row.details or '')[:40]}"
    await callback.message.edit_text(
        text,
        reply_markup=inbox_kb(snapshot),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data == "admin:ops:limiter_sync")
async def admin_limiter_sync(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    from sqlalchemy import select

    sync = get_sync_service()
    subs = (
        await session.scalars(
            select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE)
        )
    ).all()
    ok = sum(1 for sub in subs if await sync.sync_limiters_for_subscription(sub))
    await safe_callback_answer(
        callback,
        f"همگام‌سازی: {ok}/{len(subs)}",
        show_alert=True,
    )
