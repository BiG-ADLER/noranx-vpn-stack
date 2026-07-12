from datetime import UTC, datetime

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings, get_settings
from bot.db.models import AdminAuditLog, Referral, TelegramUser, WalletTxType
from bot.services import bot_content
from bot.services.notification_hub import NotificationHub
from bot.services.payment.wallet import WalletService
from bot.utils.formatting import format_toman
from bot.utils.logging import get_logger

logger = get_logger("referral")


class ReferralService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def get_reward_toman(self, session: AsyncSession) -> int:
        return await bot_content.get_referral_wallet_reward_toman(session)

    async def try_credit_referrer(
        self,
        session: AsyncSession,
        bot: Bot,
        referee: TelegramUser,
    ) -> bool:
        if not referee.referred_by_id:
            logger.info(
                "referral_credit referee_id=%s result=skip reason=no_referrer",
                referee.id,
            )
            return False

        referral = await session.scalar(
            select(Referral).where(Referral.referee_id == referee.id)
        )
        if not referral or referral.rewarded_at:
            logger.info(
                "referral_credit referee_id=%s result=skip reason=already_rewarded",
                referee.id,
            )
            return False

        referrer = await session.get(TelegramUser, referral.referrer_id)
        if not referrer:
            logger.warning(
                "referral_credit referee_id=%s result=error reason=referrer_missing",
                referee.id,
            )
            return False

        amount = await self.get_reward_toman(session)
        wallet = WalletService()
        try:
            await wallet.credit(
                session,
                referrer.id,
                amount,
                WalletTxType.DEPOSIT,
                reference=f"REF-{referee.id}",
                note="پاداش دعوت",
            )
        except Exception as exc:
            logger.exception(
                "referral_credit referrer_id=%s referee_id=%s result=error",
                referrer.id,
                referee.id,
            )
            return False

        referral.rewarded_at = datetime.now(UTC)
        referral.reward_discount_id = None
        session.add(
            AdminAuditLog(
                admin_telegram_id=0,
                action="referral_wallet_credit",
                details=f"referrer_id={referrer.id} referee_id={referee.id} amount={amount}",
            )
        )
        await session.flush()

        logger.info(
            "referral_credit referrer_id=%s referee_id=%s amount=%s result=ok",
            referrer.id,
            referee.id,
            amount,
        )

        referee_label = (
            f"@{referee.username}" if referee.username else str(referee.telegram_id)
        )
        try:
            await bot.send_message(
                referrer.telegram_id,
                f"🎁 کاربر {referee_label} با لینک شما عضو شد.\n"
                f"{format_toman(amount)} به کیف پول شما اضافه شد.",
            )
        except Exception:
            pass

        try:
            hub = NotificationHub(bot, session)
            await hub.alert(
                "referral_wallet",
                f"👥 پاداش دعوت\nمعرف: <code>{referrer.telegram_id}</code>\n"
                f"دعوت‌شده: <code>{referee.telegram_id}</code>\n"
                f"مبلغ: {format_toman(amount)}",
                severity="info",
                context=f"referee:{referee.id}",
                to_admins=False,
                to_ops=True,
                throttle=True,
            )
        except Exception:
            pass

        return True
