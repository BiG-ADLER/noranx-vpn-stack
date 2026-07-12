from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Referral, TelegramUser, WalletTransaction, WalletTxType
from bot.keyboards.user import back_main_kb
from bot.services import bot_content
from bot.utils.formatting import format_toman

router = Router()


@router.callback_query(F.data == "menu:referral")
async def referral_info(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not user:
        await callback.answer("ابتدا /start بزنید.", show_alert=True)
        return

    reward_toman = await bot_content.get_referral_wallet_reward_toman(session)
    me = await callback.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user.referral_code}"

    referred_count = await session.scalar(
        select(func.count())
        .select_from(TelegramUser)
        .where(TelegramUser.referred_by_id == user.id)
    )
    rewarded_count = await session.scalar(
        select(func.count())
        .select_from(Referral)
        .where(Referral.referrer_id == user.id, Referral.rewarded_at.is_not(None))
    )
    total_earned = await session.scalar(
        select(func.coalesce(func.sum(WalletTransaction.amount_toman), 0))
        .where(
            WalletTransaction.user_id == user.id,
            WalletTransaction.tx_type == WalletTxType.DEPOSIT,
            WalletTransaction.note == "پاداش دعوت",
        )
    )

    await callback.message.edit_text(
        "👥 <b>دعوت از دوستان</b>\n\n"
        f"لینک دعوت:\n<code>{link}</code>\n\n"
        f"دعوت‌شده‌ها: <code>{referred_count or 0}</code>\n"
        f"پاداش دریافت‌شده: <code>{rewarded_count or 0}</code> نفر\n"
        f"جمع پاداش کیف پول: {format_toman(int(total_earned or 0))}\n\n"
        f"وقتی دوست شما با لینک شما عضو کانال شود، "
        f"{format_toman(reward_toman)} به کیف پول شما اضافه می‌شود.",
        reply_markup=back_main_kb(),
        parse_mode="HTML",
    )
    await callback.answer()
