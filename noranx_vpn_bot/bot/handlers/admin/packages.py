from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import RechargePackage
from bot.keyboards.common import cancel_fsm_kb
from bot.states import AdminStates
from bot.utils.admin_ui import admin_guard
from bot.utils.telegram import safe_callback_answer

router = Router()


def _packages_list_kb(packages: list[RechargePackage]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if p.is_active else '⛔'} {p.amount_toman:,} تومان",
                callback_data=f"admin:package:view:{p.id}",
            )
        ]
        for p in packages
    ]
    rows.append([InlineKeyboardButton(text="➕ بسته جدید", callback_data="admin:package:create")])
    rows.append([InlineKeyboardButton(text="« فروش", callback_data="admin:hub:commerce")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _package_actions_kb(pkg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ مبلغ", callback_data=f"admin:package:edit:{pkg_id}"),
                InlineKeyboardButton(text="🔀 فعال/غیرفعال", callback_data=f"admin:package:toggle:{pkg_id}"),
            ],
            [
                InlineKeyboardButton(text="↑", callback_data=f"admin:package:up:{pkg_id}"),
                InlineKeyboardButton(text="↓", callback_data=f"admin:package:down:{pkg_id}"),
            ],
            [InlineKeyboardButton(text="« بسته‌ها", callback_data="admin:packages")],
        ]
    )


@router.callback_query(F.data == "admin:packages")
async def admin_packages(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await admin_guard(callback):
        return
    pkgs = (
        await session.scalars(select(RechargePackage).order_by(RechargePackage.sort_order, RechargePackage.id))
    ).all()
    await callback.message.edit_text(
        "📦 <b>بسته‌های شارژ</b>\nروی هر بسته بزنید برای مدیریت.",
        reply_markup=_packages_list_kb(list(pkgs)),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:package:view:"))
async def admin_package_view(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await admin_guard(callback):
        return
    pkg_id = int(callback.data.split(":")[-1])
    pkg = await session.get(RechargePackage, pkg_id)
    if not pkg:
        await safe_callback_answer(callback, "یافت نشد.", show_alert=True)
        return
    await callback.message.edit_text(
        f"📦 بسته #{pkg.id}\n"
        f"مبلغ: {pkg.amount_toman:,} تومان\n"
        f"وضعیت: {'فعال' if pkg.is_active else 'غیرفعال'}\n"
        f"ترتیب: {pkg.sort_order}",
        reply_markup=_package_actions_kb(pkg.id),
        parse_mode=None,
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data == "admin:package:create")
async def admin_package_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.set_state(AdminStates.package_edit_amount)
    await state.update_data(package_action="create")
    await callback.message.answer("مبلغ بسته جدید (تومان):", reply_markup=cancel_fsm_kb())
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:package:edit:"))
async def admin_package_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    pkg_id = int(callback.data.split(":")[-1])
    await state.set_state(AdminStates.package_edit_amount)
    await state.update_data(package_action="edit", package_id=pkg_id)
    await callback.message.answer("مبلغ جدید (تومان):", reply_markup=cancel_fsm_kb())
    await safe_callback_answer(callback)


@router.message(AdminStates.package_edit_amount)
async def admin_package_amount(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    data = await state.get_data()
    await state.clear()
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        await message.answer("عدد نامعتبر.")
        return
    if data.get("package_action") == "create":
        max_sort = await session.scalar(select(func.max(RechargePackage.sort_order))) or 0
        pkg = RechargePackage(amount_toman=amount, sort_order=max_sort + 1)
        session.add(pkg)
        await session.flush()
        await message.answer(f"✅ بسته {amount:,} تومان اضافه شد.", reply_markup=_package_actions_kb(pkg.id))
        return
    pkg_id = data.get("package_id")
    pkg = await session.get(RechargePackage, pkg_id)
    if not pkg:
        await message.answer("بسته یافت نشد.")
        return
    pkg.amount_toman = amount
    await session.flush()
    await message.answer(f"✅ بسته #{pkg.id} به {amount:,} تومان تغییر کرد.", reply_markup=_package_actions_kb(pkg.id))


@router.callback_query(F.data.startswith("admin:package:toggle:"))
async def admin_package_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await admin_guard(callback):
        return
    pkg_id = int(callback.data.split(":")[-1])
    pkg = await session.get(RechargePackage, pkg_id)
    if not pkg:
        await safe_callback_answer(callback, "یافت نشد.", show_alert=True)
        return
    pkg.is_active = not pkg.is_active
    await session.commit()
    await safe_callback_answer(callback, f"{'فعال' if pkg.is_active else 'غیرفعال'}", show_alert=True)
    await admin_package_view(callback, session)


@router.callback_query(F.data.startswith("admin:package:up:"))
@router.callback_query(F.data.startswith("admin:package:down:"))
async def admin_package_reorder(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await admin_guard(callback):
        return
    pkg_id = int(callback.data.split(":")[-1])
    direction = callback.data.split(":")[2]
    pkg = await session.get(RechargePackage, pkg_id)
    if not pkg:
        await safe_callback_answer(callback, "یافت نشد.", show_alert=True)
        return
    pkgs = (
        await session.scalars(select(RechargePackage).order_by(RechargePackage.sort_order, RechargePackage.id))
    ).all()
    idx = next((i for i, p in enumerate(pkgs) if p.id == pkg_id), None)
    if idx is None:
        await safe_callback_answer(callback)
        return
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap_idx < len(pkgs):
        other = pkgs[swap_idx]
        pkg.sort_order, other.sort_order = other.sort_order, pkg.sort_order
        await session.commit()
    await admin_packages(callback, session)


@router.message(Command("package_add"))
async def package_add_cmd(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    await state.set_state(AdminStates.package_edit_amount)
    await state.update_data(package_action="create")
    await message.answer("مبلغ بسته جدید (تومان):", reply_markup=cancel_fsm_kb())
