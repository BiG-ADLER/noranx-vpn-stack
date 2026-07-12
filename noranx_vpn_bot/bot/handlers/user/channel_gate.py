from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import TelegramUser
from bot.keyboards.admin import admin_menu_kb
from bot.keyboards.admin_reply import admin_reply_kb
from bot.keyboards.channel_gate import channel_gate_kb
from bot.keyboards.user import main_menu_kb, onboarding_kb
from bot.services import bot_content
from bot.services.admin_ops import build_ops_snapshot
from bot.services.channel_gate import (
    GATE_MESSAGE,
    invalidate_member_cache,
    is_channel_member,
    is_exempt,
    resolve_channel_link,
)
from bot.services.referral import ReferralService
from bot.utils.telegram import safe_callback_answer

router = Router()
referral_service = ReferralService()


async def _admin_panel_text(session: AsyncSession) -> str:
    return await bot_content.get_admin_panel_title(session)


async def _show_welcome(
    message_or_callback,
    session: AsyncSession,
    *,
    user: TelegramUser,
    created: bool,
    is_admin: bool,
) -> None:
    from aiogram.types import InlineKeyboardMarkup, Message

    active_count = 0
    if user:
        from bot.db.models import Subscription, SubscriptionStatus

        active_count = await session.scalar(
            select(Subscription.id)
            .where(
                Subscription.user_id == user.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
            .limit(1)
        )
        active_count = 1 if active_count else 0

    is_new_onboarding = created and not active_count and not is_admin
    if is_new_onboarding:
        text = await bot_content.get_welcome_text(session, is_new=True)
    else:
        text = await bot_content.get_welcome_text(session)
    if created and user.referred_by_id:
        text += "\n\n✅ کد دعوت شما ثبت شد."

    reply_markup = main_menu_kb(is_admin)
    if is_new_onboarding:
        main_rows = main_menu_kb(is_admin).inline_keyboard
        onboard_rows = onboarding_kb().inline_keyboard
        reply_markup = InlineKeyboardMarkup(inline_keyboard=onboard_rows + main_rows)
    elif is_admin:
        bot = message_or_callback.bot
        chat_id = (
            message_or_callback.chat.id
            if isinstance(message_or_callback, Message)
            else message_or_callback.message.chat.id
        )
        await bot.send_message(chat_id, text, reply_markup=admin_reply_kb())
        snapshot = await build_ops_snapshot(session)
        await bot.send_message(
            chat_id,
            await _admin_panel_text(session),
            reply_markup=admin_menu_kb(snapshot),
        )
        return

    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=reply_markup)
    else:
        await message_or_callback.message.edit_text(text, reply_markup=reply_markup)


@router.callback_query(F.data == "channel:recheck")
async def channel_recheck(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    settings = get_settings()
    if not settings.required_channel_id:
        await safe_callback_answer(callback)
        return

    user_id = callback.from_user.id
    invalidate_member_cache(user_id)

    try:
        if not await is_channel_member(callback.bot, user_id):
            link = await resolve_channel_link(callback.bot)
            await callback.message.edit_text(
                "هنوز عضو کانال نیستید. پس از عضویت «بررسی عضویت» را بزنید.",
                reply_markup=channel_gate_kb(link),
            )
            await safe_callback_answer(callback, "هنوز عضو کانال نیستید.", show_alert=True)
            return
    except Exception:
        await safe_callback_answer(callback, "خطا در بررسی عضویت.", show_alert=True)
        return

    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == user_id)
    )
    if user:
        await referral_service.try_credit_referrer(session, callback.bot, user)

    await state.clear()
    is_admin = user_id in settings.admin_ids

    if user:
        await _show_welcome(callback, session, user=user, created=False, is_admin=is_admin)
    else:
        await callback.message.edit_text("✅ عضویت کانال تأیید شد. /start را بزنید.")

    await safe_callback_answer(callback, "عضویت تأیید شد!")
