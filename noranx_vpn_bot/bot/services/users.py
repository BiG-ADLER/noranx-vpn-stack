from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Referral, TelegramUser
from bot.utils.username import generate_referral_code


class UserService:
    async def get_or_create(
        self,
        session: AsyncSession,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        referral_code_from_start: str | None = None,
    ) -> tuple[TelegramUser, bool]:
        user = await session.scalar(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        )
        if user:
            if username:
                user.username = username
            if first_name:
                user.first_name = first_name
            await session.flush()
            return user, False

        code = generate_referral_code()
        while await session.scalar(select(TelegramUser).where(TelegramUser.referral_code == code)):
            code = generate_referral_code()

        referrer_id = None
        if referral_code_from_start:
            ref_code = referral_code_from_start.removeprefix("ref_").upper()
            referrer = await session.scalar(
                select(TelegramUser).where(TelegramUser.referral_code == ref_code)
            )
            if referrer and referrer.telegram_id != telegram_id:
                referrer_id = referrer.id

        user = TelegramUser(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            referral_code=code,
            referred_by_id=referrer_id,
        )
        session.add(user)
        await session.flush()

        if referrer_id:
            session.add(Referral(referrer_id=referrer_id, referee_id=user.id))
            await session.flush()

        return user, True
