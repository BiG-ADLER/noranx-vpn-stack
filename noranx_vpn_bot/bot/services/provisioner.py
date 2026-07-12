import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db.models import (
    Order,
    OrderItem,
    OrderStatus,
    Plan,
    ProvisioningLog,
    Subscription,
    SubscriptionStatus,
    TelegramUser,
)
from bot.services.ip_limiter import IpLimiterService
from bot.services.marzban import MarzbanService
from bot.utils.logging import get_logger
from bot.utils.subscription_url import normalize_subscription_url
from bot.utils.username import generate_marzban_username

logger = get_logger("provisioner")


@dataclass
class ProvisionResult:
    subscription: Subscription | None
    success: bool
    error: str | None = None


class ProvisionerService:
    def __init__(
        self,
        settings: Settings,
        marzban: MarzbanService,
        ip_limiter: IpLimiterService,
    ) -> None:
        self._settings = settings
        self._marzban = marzban
        self._ip_limiter = ip_limiter

    async def _log(
        self,
        session: AsyncSession,
        *,
        correlation_id: str,
        step: str,
        service: str,
        ok: bool,
        order_id: int | None = None,
        subscription_id: int | None = None,
        request_summary: str | None = None,
        response_summary: str | None = None,
        error: str | None = None,
    ) -> None:
        session.add(
            ProvisioningLog(
                correlation_id=correlation_id,
                order_id=order_id,
                subscription_id=subscription_id,
                step=step,
                service=service,
                ok=ok,
                request_summary=request_summary,
                response_summary=response_summary,
                error=error,
            )
        )
        await session.flush()

    async def _rollback_external(self, username: str) -> None:
        try:
            await self._ip_limiter.remove_limit(username)
        except Exception:
            pass
        try:
            await self._marzban.delete_user(username)
        except Exception:
            pass

    async def provision_one(
        self,
        session: AsyncSession,
        *,
        user: TelegramUser,
        plan: Plan | None,
        device_limit: int,
        data_limit: int,
        duration_days: int,
        is_trial: bool,
        correlation_id: str,
        order_id: int | None = None,
        note: str = "",
        preferred_username: str | None = None,
    ) -> ProvisionResult:
        if preferred_username:
            username = preferred_username
            username_source = "preferred"
        else:
            username = generate_marzban_username(user.telegram_id, prefix="t" if is_trial else "")
            username_source = "generated"
        logger.info(
            "provision_username order_id=%s username=%s source=%s",
            order_id,
            username,
            username_source,
        )
        expire_at = datetime.now(UTC) + timedelta(days=duration_days)
        expire_ts = int(expire_at.timestamp())

        try:
            mb_user = await self._marzban.create_user(
                username=username,
                data_limit=data_limit,
                expire_timestamp=expire_ts,
                note=note,
            )
            await self._log(
                session,
                correlation_id=correlation_id,
                step="marzban_create",
                service="marzban",
                ok=True,
                order_id=order_id,
                request_summary=f"user={username} limit={data_limit}",
                response_summary=mb_user.subscription_url or "",
            )
        except Exception as e:
            await self._log(
                session,
                correlation_id=correlation_id,
                step="marzban_create",
                service="marzban",
                ok=False,
                order_id=order_id,
                error=str(e),
            )
            return ProvisionResult(None, False, str(e))

        if self._settings.provision_skip_limiters:
            await self._log(
                session,
                correlation_id=correlation_id,
                step="ip_limit",
                service="ip_limiter",
                ok=False,
                order_id=order_id,
                error="skipped (PROVISION_SKIP_LIMITERS)",
            )
        else:
            try:
                await self._ip_limiter.set_limit(username, device_limit)
                await self._log(
                    session,
                    correlation_id=correlation_id,
                    step="ip_limit",
                    service="ip_limiter",
                    ok=True,
                    order_id=order_id,
                    request_summary=f"limit={device_limit}",
                )
            except Exception as e:
                await self._log(
                    session,
                    correlation_id=correlation_id,
                    step="ip_limit",
                    service="ip_limiter",
                    ok=False,
                    order_id=order_id,
                    error=str(e),
                )
                await self._rollback_external(username)
                return ProvisionResult(None, False, f"ip_limiter failed: {e}")

        sub = Subscription(
            user_id=user.id,
            plan_id=plan.id if plan else None,
            marzban_username=username,
            subscription_url=normalize_subscription_url(mb_user.subscription_url),
            device_limit=device_limit,
            ip_limit=device_limit,
            is_trial=is_trial,
            expires_at=expire_at,
            status=SubscriptionStatus.ACTIVE,
            data_limit_bytes=mb_user.data_limit if mb_user.data_limit else (data_limit or None),
        )
        session.add(sub)
        await session.flush()
        await self._log(
            session,
            correlation_id=correlation_id,
            step="db_save",
            service="database",
            ok=True,
            order_id=order_id,
            subscription_id=sub.id,
        )
        return ProvisionResult(sub, True)

    async def provision_order(self, session: AsyncSession, order: Order, plan: Plan) -> list[ProvisionResult]:
        correlation_id = f"ORD-{order.id}"
        order.status = OrderStatus.PROVISIONING
        await session.flush()

        user = await session.get(TelegramUser, order.user_id)
        if not user:
            order.status = OrderStatus.FAILED
            return []

        results: list[ProvisionResult] = []
        for i in range(order.quantity):
            item = OrderItem(order_id=order.id, success=False)
            session.add(item)
            await session.flush()

            note = f"plan:{plan.slug}|tg:{user.telegram_id}|order:{order.id}|item:{i+1}"
            preferred = order.preferred_username if i == 0 else None
            result = await self.provision_one(
                session,
                user=user,
                plan=plan,
                device_limit=plan.device_count,
                data_limit=0,
                duration_days=plan.duration_days,
                is_trial=False,
                correlation_id=correlation_id,
                order_id=order.id,
                note=note,
                preferred_username=preferred,
            )
            if result.success and result.subscription:
                item.subscription_id = result.subscription.id
                item.success = True
            results.append(result)

        successes = sum(1 for r in results if r.success)
        if successes == order.quantity:
            order.status = OrderStatus.COMPLETED
        elif successes > 0:
            order.status = OrderStatus.COMPLETED
        else:
            order.status = OrderStatus.FAILED
        await session.flush()
        return results

    async def provision_trial(self, session: AsyncSession, user: TelegramUser) -> ProvisionResult:
        correlation_id = f"TRIAL-{user.telegram_id}-{int(time.time())}"
        return await self.provision_one(
            session,
            user=user,
            plan=None,
            device_limit=1,
            data_limit=self._settings.trial_data_limit_bytes,
            duration_days=self._settings.trial_duration_days,
            is_trial=True,
            correlation_id=correlation_id,
            note=f"trial|tg:{user.telegram_id}",
        )

    async def renew_subscription(
        self, session: AsyncSession, subscription: Subscription, plan: Plan
    ) -> bool:
        expire_at = datetime.now(UTC) + timedelta(days=plan.duration_days)
        expire_ts = int(expire_at.timestamp())
        try:
            await self._marzban.modify_user(
                subscription.marzban_username,
                expire=expire_ts,
                status="active",
                data_limit=0,
            )
            subscription.expires_at = expire_at
            subscription.status = SubscriptionStatus.ACTIVE
            await self._ip_limiter.set_limit(subscription.marzban_username, plan.device_count)
            subscription.device_limit = plan.device_count
            subscription.ip_limit = plan.device_count
            await session.flush()
            return True
        except Exception as e:
            logger.exception("Renew failed for %s: %s", subscription.marzban_username, e)
            return False

    async def re_enable(self, subscription: Subscription) -> bool:
        try:
            await self._marzban.modify_user(subscription.marzban_username, status="active")
            await self._ip_limiter.set_limit(subscription.marzban_username, subscription.ip_limit)
            return True
        except Exception as e:
            logger.exception("Re-enable failed: %s", e)
            return False
