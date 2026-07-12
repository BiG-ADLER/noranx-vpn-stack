from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Subscription, SubscriptionStatus
from bot.services.ip_limiter import IpLimiterService
from bot.services.marzban import MarzbanService
from bot.utils.logging import get_logger
from bot.utils.subscription_url import normalize_subscription_url

logger = get_logger("sync")


class SyncService:
    def __init__(
        self,
        marzban: MarzbanService,
        ip_limiter: IpLimiterService,
    ) -> None:
        self._marzban = marzban
        self._ip_limiter = ip_limiter

    async def sync_subscription(self, session: AsyncSession, sub: Subscription) -> None:
        mb = await self._marzban.get_user(sub.marzban_username)
        await self.apply_marzban_user(session, sub, mb)

    async def apply_marzban_user(
        self, session: AsyncSession, sub: Subscription, mb
    ) -> None:
        if not mb:
            sub.status = SubscriptionStatus.PROVISIONING_FAILED
            return
        sub.used_traffic_bytes = mb.used_traffic
        if mb.data_limit:
            sub.data_limit_bytes = mb.data_limit
        if mb.status == "disabled":
            sub.status = SubscriptionStatus.DISABLED
        elif mb.status == "limited":
            sub.status = SubscriptionStatus.LIMITED
        elif mb.expire and mb.expire < int(datetime.now(UTC).timestamp()):
            sub.status = SubscriptionStatus.EXPIRED
        else:
            sub.status = SubscriptionStatus.ACTIVE
            if mb.expire:
                sub.expires_at = datetime.fromtimestamp(mb.expire, tz=UTC)
        if mb.subscription_url:
            sub.subscription_url = normalize_subscription_url(mb.subscription_url)
        await session.flush()

    async def sync_limiters_for_subscription(self, sub: Subscription) -> bool:
        try:
            await self._ip_limiter.set_limit(sub.marzban_username, sub.ip_limit)
            return True
        except Exception as e:
            logger.warning("limiter sync failed %s: %s", sub.marzban_username, e)
            return False

    async def count_limiter_drift(self, session: AsyncSession) -> int:
        subs = (
            await session.scalars(
                select(Subscription).where(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                )
            )
        ).all()
        drift = 0
        for sub in subs:
            if await self._ip_limiter_drifted(sub):
                drift += 1
        return drift

    async def _ip_limiter_drifted(self, sub: Subscription) -> bool:
        try:
            lim = await self._ip_limiter.get_limit(sub.marzban_username)
            if not lim or not lim.get("configured"):
                return True
            configured = lim.get("limit")
            if configured is None or int(configured) != sub.ip_limit:
                return True
        except Exception:
            return True
        return False
