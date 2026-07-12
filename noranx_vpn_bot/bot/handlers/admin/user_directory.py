from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.admin.users import _is_admin, show_user_card
from bot.keyboards.admin_hubs import users_hub_kb
from bot.keyboards.common import cancel_fsm_kb
from bot.services.audience import SEGMENT_LABELS, AudienceSegment, list_users, user_badges_batch
from bot.utils.telegram import safe_callback_answer

router = Router()


def _dir_kb(
    segment: str,
    page: int,
    total: int,
    *,
    page_size: int = 15,
    sort: str = "newest",
) -> InlineKeyboardMarkup:
    rows = []
    max_page = max(0, (total - 1) // page_size)
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀", callback_data=f"admin:dir:{segment}:{page - 1}:{page_size}:{sort}"
            )
        )
    nav.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{max_page + 1}",
            callback_data=f"admin:dir:{segment}:{page}:{page_size}:{sort}",
        )
    )
    if page < max_page:
        nav.append(
            InlineKeyboardButton(
                text="▶", callback_data=f"admin:dir:{segment}:{page + 1}:{page_size}:{sort}"
            )
        )
    rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(
                text=f"10{'✓' if page_size == 10 else ''}",
                callback_data=f"admin:dir:{segment}:0:10:{sort}",
            ),
            InlineKeyboardButton(
                text=f"20{'✓' if page_size == 20 else ''}",
                callback_data=f"admin:dir:{segment}:0:20:{sort}",
            ),
            InlineKeyboardButton(
                text=f"30{'✓' if page_size == 30 else ''}",
                callback_data=f"admin:dir:{segment}:0:30:{sort}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=f"جدیدترین{'✓' if sort == 'newest' else ''}",
                callback_data=f"admin:dir:{segment}:0:{page_size}:newest",
            ),
            InlineKeyboardButton(
                text=f"قدیمی‌ترین{'✓' if sort == 'oldest' else ''}",
                callback_data=f"admin:dir:{segment}:0:{page_size}:oldest",
            ),
            InlineKeyboardButton(
                text=f"کیف پول{'✓' if sort == 'wallet' else ''}",
                callback_data=f"admin:dir:{segment}:0:{page_size}:wallet",
            ),
        ]
    )
    rows.append([InlineKeyboardButton(text="🔎 جستجو", callback_data="admin:users:search")])
    rows.append([InlineKeyboardButton(text="« کاربران", callback_data="admin:hub:users")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:hub:users")
async def users_hub(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "👥 <b>کاربران و پیام‌رسانی</b>",
        reply_markup=users_hub_kb(),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data == "admin:users:search")
async def users_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    from bot.states import AdminStates

    if not _is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.search_user)
    await callback.message.edit_text(
        "🔍 شناسه تلگرام، @username یا marzban_username:",
        reply_markup=cancel_fsm_kb(),
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.regexp(r"^admin:dir:[a-z_]+:\d+(?::\d+:(?:newest|oldest|wallet))?$"))
async def user_directory(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    segment_str = parts[2]
    page = int(parts[3])
    page_size = int(parts[4]) if len(parts) > 4 else 15
    sort = parts[5] if len(parts) > 5 else "newest"
    try:
        segment = AudienceSegment(segment_str)
    except ValueError:
        await safe_callback_answer(callback, "فیلتر نامعتبر.", show_alert=True)
        return
    users, total = await list_users(session, segment, page=page, page_size=page_size, sort=sort)
    label = SEGMENT_LABELS.get(segment, segment_str)
    lines = [
        f"📊 <b>{label}</b> — {total} کاربر",
        f"فیلتر فعال: <code>{segment.value}</code> | نمایش: <code>{page_size}</code> | مرتب‌سازی: <code>{sort}</code>\n",
    ]
    kb_rows = []
    badge_map = await user_badges_batch(session, [u.id for u in users])
    for u in users:
        name = f"@{u.username}" if u.username else (u.first_name or str(u.telegram_id))
        badge = badge_map.get(u.id, "👤")
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text=f"{badge} {name[:22]} ({u.telegram_id})",
                    callback_data=f"admin:user:view:{u.telegram_id}",
                )
            ]
        )
    kb_rows.extend(
        _dir_kb(segment_str, page, total, page_size=page_size, sort=sort).inline_keyboard
    )
    await callback.message.edit_text(
        "\n".join(lines) if users else f"📊 <b>{label}</b>\n\nکاربری یافت نشد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:user:view:"))
async def user_view(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    tg_id = int(callback.data.split(":")[-1])
    await show_user_card(callback.message, session, tg_id, edit=True)
    await safe_callback_answer(callback)


@router.message(Command("dir_page"))
async def dir_page_cmd(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("استفاده: /dir_page <segment> <page>\nمثال: /dir_page active_subscribers 2")
        return
    segment = parts[1].strip()
    page = parts[2].strip()
    if not page.isdigit():
        await message.answer("شماره صفحه باید عدد باشد.")
        return
    await message.answer(
        "باز کردن صفحه...",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"📄 {segment} صفحه {int(page)+1}",
                        callback_data=f"admin:dir:{segment}:{int(page)}:20:newest",
                    )
                ]
            ]
        ),
    )
