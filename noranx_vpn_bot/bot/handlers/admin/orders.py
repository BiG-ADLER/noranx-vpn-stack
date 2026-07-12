from aiogram import F, Router
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import Order, OrderStatus, ProvisioningLog
from bot.handlers.user.shop import _get_services
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.admin import admin_orders_kb
from bot.services.order_retry import retry_order
from bot.utils.telegram import safe_callback_answer

router = Router()


async def _last_errors_batch(session: AsyncSession, order_ids: list[int]) -> dict[int, str]:
    if not order_ids:
        return {}
    rn = func.row_number().over(
        partition_by=ProvisioningLog.order_id,
        order_by=ProvisioningLog.id.desc(),
    ).label("rn")
    subq = (
        select(
            ProvisioningLog.order_id,
            ProvisioningLog.error,
            ProvisioningLog.response_summary,
            rn,
        )
        .where(ProvisioningLog.order_id.in_(order_ids), ProvisioningLog.ok.is_(False))
        .subquery()
    )
    rows = (
        await session.execute(
            select(subq.c.order_id, subq.c.error, subq.c.response_summary).where(subq.c.rn == 1)
        )
    ).all()
    out: dict[int, str] = {}
    for order_id, error, summary in rows:
        err = error or summary or ""
        out[order_id] = err[:80] + ("…" if len(err) > 80 else "")
    return out


@router.callback_query(F.data == "admin:orders")
async def admin_orders(callback, session: AsyncSession) -> None:
    if callback.from_user.id not in get_settings().admin_ids:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    stuck = (
        await session.scalars(
            select(Order).where(Order.status == OrderStatus.PROVISIONING).limit(10)
        )
    ).all()
    failed = (
        await session.scalars(
            select(Order).where(Order.status == OrderStatus.FAILED).limit(10)
        )
    ).all()
    problem = stuck + failed
    error_map = await _last_errors_batch(session, [o.id for o in problem])
    lines = ["📋 <b>سفارش‌های مشکل‌دار</b>", f"گیرکرده: {len(stuck)} | ناموفق: {len(failed)}"]
    for o in problem:
        err = error_map.get(o.id, "")
        line = f"#{o.id} — {o.status.value} — {o.total_toman:,} ت"
        if err:
            line += f"\n  ❌ {err}"
        lines.append(line)
    text = "\n".join(lines) if problem else "سفارش مشکلی نیست."
    kb = admin_orders_kb([o.id for o in problem]) if problem else InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="« زیرساخت", callback_data="admin:hub:infra")]]
    )
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:order:retry:"))
async def admin_order_retry(callback, session: AsyncSession) -> None:
    if callback.from_user.id not in get_settings().admin_ids:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    order_id = int(callback.data.split(":")[-1])
    result = await retry_order(
        session, order_id, _get_services(), callback.from_user.id
    )
    await safe_callback_answer(callback, result.message, show_alert=True)
    from bot.keyboards.admin_hubs import infra_hub_kb

    await callback.message.answer(result.message, reply_markup=infra_hub_kb())


@router.callback_query(F.data.startswith("admin:order:logs:"))
async def admin_order_logs_cb(callback, session: AsyncSession) -> None:
    if callback.from_user.id not in get_settings().admin_ids:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    order_id = int(callback.data.split(":")[-1])
    logs = (
        await session.scalars(
            select(ProvisioningLog)
            .where(ProvisioningLog.order_id == order_id)
            .order_by(ProvisioningLog.id.desc())
            .limit(20)
        )
    ).all()
    if not logs:
        await callback.answer("لاگی نیست.", show_alert=True)
        return
    text = "\n".join(
        f"{'✅' if l.ok else '❌'} {l.step}/{l.service}: {l.error or l.response_summary or ''}"
        for l in logs
    )
    await callback.message.answer(text[:4000])
    await callback.answer()


@router.message(F.text.startswith("/order_logs"))
async def order_logs(message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    try:
        order_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("/order_logs order_id", parse_mode=None)
        return
    logs = (
        await session.scalars(
            select(ProvisioningLog)
            .where(ProvisioningLog.order_id == order_id)
            .order_by(ProvisioningLog.id.desc())
            .limit(20)
        )
    ).all()
    if not logs:
        await message.answer("لاگی نیست.")
        return
    text = "\n".join(
        f"{'✅' if l.ok else '❌'} {l.step}/{l.service}: {l.error or l.response_summary or ''}"
        for l in logs
    )
    await message.answer(text[:4000])
