from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import TelegramUser
from bot.keyboards.user import back_main_kb
from bot.services.ip_limiter import IpLimiterService
from bot.services.marzban import MarzbanService
from bot.services.provisioner import ProvisionerService
from bot.utils.subscription_delivery import send_subscription_details

router = Router()


@router.callback_query(F.data == "menu:trial")
async def trial_start(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await session.scalar(
        select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
    )
    if not user:
        await callback.answer("ابتدا /start بزنید.", show_alert=True)
        return
    if user.trial_used:
        await callback.answer("شما قبلاً از تست رایگان استفاده کرده‌اید.", show_alert=True)
        return

    settings = get_settings()
    provisioner = ProvisionerService(
        settings,
        MarzbanService(settings),
        IpLimiterService(settings),
    )
    result = await provisioner.provision_trial(session, user)
    if not result.success or not result.subscription:
        await callback.message.answer(
            f"❌ خطا در ایجاد تست: {result.error}",
            reply_markup=back_main_kb(),
        )
        await callback.answer()
        return

    user.trial_used = True
    await session.flush()
    sub = result.subscription
    await callback.message.answer(
        "✅ تست رایگان فعال شد!\n⏳ ۱ روز | 📊 ۱۰۰ مگابایت | 📱 ۱ دستگاه",
        reply_markup=back_main_kb(),
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    await callback.message.answer(
        "📖 برای اتصال راهنما را ببینید:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📖 راهنمای اتصال", callback_data="menu:guide")]
            ]
        ),
    )
    await send_subscription_details(
        callback.bot,
        callback.from_user.id,
        marzban_username=sub.marzban_username,
        subscription_url=sub.subscription_url,
        device_limit=sub.device_limit,
        qr_caption="QR تست",
    )
    await callback.answer()
