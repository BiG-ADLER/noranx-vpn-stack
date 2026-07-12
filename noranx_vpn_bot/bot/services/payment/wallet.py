from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import TelegramUser, WalletTransaction, WalletTxType


class WalletService:
    async def get_balance(self, session: AsyncSession, user_id: int) -> int:
        user = await session.get(TelegramUser, user_id)
        return user.wallet_balance_toman if user else 0

    async def credit(
        self,
        session: AsyncSession,
        user_id: int,
        amount: int,
        tx_type: WalletTxType,
        reference: str | None = None,
        note: str | None = None,
    ) -> int:
        result = await session.execute(
            select(TelegramUser).where(TelegramUser.id == user_id).with_for_update()
        )
        user = result.scalar_one()
        user.wallet_balance_toman += amount
        session.add(
            WalletTransaction(
                user_id=user_id,
                amount_toman=amount,
                balance_after=user.wallet_balance_toman,
                tx_type=tx_type,
                reference=reference,
                note=note,
            )
        )
        await session.flush()
        return user.wallet_balance_toman

    async def debit(
        self,
        session: AsyncSession,
        user_id: int,
        amount: int,
        reference: str | None = None,
        note: str | None = None,
    ) -> int:
        if amount <= 0:
            raise ValueError("amount must be positive")
        result = await session.execute(
            select(TelegramUser).where(TelegramUser.id == user_id).with_for_update()
        )
        user = result.scalar_one()
        if user.wallet_balance_toman < amount:
            raise ValueError("insufficient balance")
        user.wallet_balance_toman -= amount
        session.add(
            WalletTransaction(
                user_id=user_id,
                amount_toman=-amount,
                balance_after=user.wallet_balance_toman,
                tx_type=WalletTxType.PURCHASE,
                reference=reference,
                note=note,
            )
        )
        await session.flush()
        return user.wallet_balance_toman
