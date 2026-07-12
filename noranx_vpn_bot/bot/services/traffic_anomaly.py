import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db.models import (
    AdminAuditLog,
    Subscription,
    SubscriptionStatus,
    TrafficAnomalyEvent,
    TrafficAnomalyStatus,
    TrafficUsageSnapshot,
)
from bot.services.marzban import MarzbanService, MarzbanUserListItem
from bot.services.notification_hub import NotificationHub
from bot.utils.logging import get_logger

logger = get_logger("traffic_anomaly")


@dataclass
class EvaluationResult:
    username: str
    score: int
    action: str
    reasons: list[str]
    delta_bytes: int
    delta_minutes: int
    rate_mbps: float
    floor_bytes: int
    baseline_bytes: int
    event_id: int | None = None


class TrafficAnomalyService:
    def __init__(self, settings: Settings, marzban: MarzbanService) -> None:
        self.settings = settings
        self.marzban = marzban

    def _floor_for_device_limit(self, device_limit: int) -> int:
        if device_limit <= 1:
            return self.settings.traffic_anomaly_floor_1_device_bytes
        if device_limit == 2:
            return self.settings.traffic_anomaly_floor_2_device_bytes
        return self.settings.traffic_anomaly_floor_3p_device_bytes

    async def _last_snapshot(
        self, session: AsyncSession, username: str
    ) -> TrafficUsageSnapshot | None:
        return await session.scalar(
            select(TrafficUsageSnapshot)
            .where(TrafficUsageSnapshot.marzban_username == username)
            .order_by(TrafficUsageSnapshot.checked_at.desc())
            .limit(1)
        )

    async def _baseline_delta_bytes(self, session: AsyncSession, username: str) -> int:
        rows = (
            await session.scalars(
                select(TrafficUsageSnapshot.used_traffic_bytes)
                .where(TrafficUsageSnapshot.marzban_username == username)
                .order_by(TrafficUsageSnapshot.checked_at.desc())
                .limit(24)
            )
        ).all()
        if len(rows) < 3:
            return 0
        deltas = []
        prev = None
        for used in reversed(rows):
            if prev is not None and used >= prev:
                deltas.append(used - prev)
            prev = used
        if not deltas:
            return 0
        deltas.sort()
        return deltas[len(deltas) // 2]

    async def _recent_anomaly_count(self, session: AsyncSession, username: str) -> int:
        since = datetime.now(UTC) - timedelta(hours=2)
        c = await session.scalar(
            select(func.count())
            .select_from(TrafficAnomalyEvent)
            .where(
                TrafficAnomalyEvent.marzban_username == username,
                TrafficAnomalyEvent.status.in_(
                    [TrafficAnomalyStatus.WATCH, TrafficAnomalyStatus.DISABLED]
                ),
                TrafficAnomalyEvent.created_at >= since,
            )
        )
        return int(c or 0)

    async def _under_cooldown(self, session: AsyncSession, username: str) -> bool:
        since = datetime.now(UTC) - timedelta(minutes=self.settings.traffic_anomaly_cooldown_minutes)
        recent = await session.scalar(
            select(TrafficAnomalyEvent.id)
            .where(
                TrafficAnomalyEvent.marzban_username == username,
                TrafficAnomalyEvent.status.in_(
                    [TrafficAnomalyStatus.WATCH, TrafficAnomalyStatus.DISABLED]
                ),
                TrafficAnomalyEvent.created_at >= since,
            )
            .limit(1)
        )
        return recent is not None

    async def _save_event(
        self,
        session: AsyncSession,
        sub: Subscription | None,
        user: MarzbanUserListItem,
        status: TrafficAnomalyStatus,
        score: int,
        reasons: list[str],
        delta_bytes: int,
        delta_minutes: int,
        rate_mbps: float,
        floor_bytes: int,
        baseline_bytes: int,
        action_taken: str,
    ) -> TrafficAnomalyEvent:
        event = TrafficAnomalyEvent(
            subscription_id=sub.id if sub else None,
            marzban_username=user.username,
            status=status,
            score=score,
            delta_bytes=delta_bytes,
            delta_minutes=delta_minutes,
            rate_mbps=rate_mbps,
            device_limit=sub.device_limit if sub else 1,
            threshold_floor_bytes=floor_bytes,
            baseline_bytes=baseline_bytes,
            reasons_json=json.dumps(reasons, ensure_ascii=True),
            action_taken=action_taken,
        )
        session.add(event)
        await session.flush()
        return event

    async def _alert(
        self,
        bot: Bot,
        session: AsyncSession,
        result: EvaluationResult,
        status: TrafficAnomalyStatus,
    ) -> None:
        hub = NotificationHub(bot, session)
        sev = "error" if status == TrafficAnomalyStatus.DISABLED else "warning"
        text = (
            f"Traffic anomaly ({status.value})\n"
            f"user: <code>{result.username}</code>\n"
            f"score: {result.score}\n"
            f"delta: {result.delta_bytes:,} bytes / {max(result.delta_minutes, 1)} min\n"
            f"rate: {result.rate_mbps:.3f} Mbps\n"
            f"reasons: {', '.join(result.reasons) if result.reasons else '-'}"
        )
        buttons = [
            ("👤 View", f"admin:marzban:view:{result.username}"),
        ]
        if result.event_id is not None and status == TrafficAnomalyStatus.DISABLED:
            buttons.append(("♻️ Re-enable", f"admin:anomaly:reenable:{result.event_id}"))
        await hub.alert(
            "traffic_anomaly",
            text,
            severity=sev,
            context=result.username,
            to_admins=True,
            to_ops=True,
            throttle=True,
            buttons=buttons,
        )

    async def evaluate_user(
        self,
        session: AsyncSession,
        user: MarzbanUserListItem,
        *,
        bot: Bot | None = None,
        dry_run: bool = False,
        sub_cache: dict[str, Subscription] | None = None,
        snapshot_cache: dict[str, TrafficUsageSnapshot] | None = None,
    ) -> EvaluationResult | None:
        if sub_cache is not None:
            sub = sub_cache.get(user.username)
        else:
            sub = await session.scalar(
                select(Subscription).where(Subscription.marzban_username == user.username)
            )
        if not sub or sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.LIMITED):
            return None

        now = datetime.now(UTC)
        if snapshot_cache is not None:
            prev = snapshot_cache.get(user.username)
        else:
            prev = await self._last_snapshot(session, user.username)
        session.add(
            TrafficUsageSnapshot(
                subscription_id=sub.id,
                marzban_username=user.username,
                used_traffic_bytes=user.used_traffic,
            )
        )
        if not prev:
            return None

        delta_bytes = max(0, int(user.used_traffic) - int(prev.used_traffic_bytes))
        delta_minutes = max(1, int((now - prev.checked_at).total_seconds() // 60))
        if delta_minutes <= 0:
            return None
        rate_mbps = float((delta_bytes * 8) / (delta_minutes * 60 * 1_000_000))

        floor_bytes = self._floor_for_device_limit(max(1, sub.device_limit))
        baseline_bytes = await self._baseline_delta_bytes(session, user.username)
        reasons: list[str] = []
        score = 0

        if delta_bytes >= floor_bytes:
            score += 2
            reasons.append("fixed_floor_exceeded")
        if baseline_bytes > 0 and delta_bytes >= int(
            baseline_bytes * self.settings.traffic_anomaly_baseline_multiplier
        ):
            score += 2
            reasons.append("baseline_multiplier_exceeded")
        if await self._recent_anomaly_count(session, user.username) >= 1:
            score += 1
            reasons.append("repeated_recently")
        if sub.data_limit_bytes and delta_bytes >= max(sub.data_limit_bytes // 2, floor_bytes):
            score += 1
            reasons.append("near_cap_pace")

        if score < self.settings.traffic_anomaly_watch_threshold:
            logger.debug(
                "traffic_anomaly normal user=%s delta=%s score=%s",
                user.username,
                delta_bytes,
                score,
            )
            return EvaluationResult(
                username=user.username,
                score=score,
                action="normal",
                reasons=reasons,
                delta_bytes=delta_bytes,
                delta_minutes=delta_minutes,
                rate_mbps=rate_mbps,
                floor_bytes=floor_bytes,
                baseline_bytes=baseline_bytes,
            )

        if await self._under_cooldown(session, user.username):
            return EvaluationResult(
                username=user.username,
                score=score,
                action="cooldown",
                reasons=reasons,
                delta_bytes=delta_bytes,
                delta_minutes=delta_minutes,
                rate_mbps=rate_mbps,
                floor_bytes=floor_bytes,
                baseline_bytes=baseline_bytes,
            )

        if score >= self.settings.traffic_anomaly_disable_threshold:
            action = "disabled" if not dry_run else "would_disable"
            event = await self._save_event(
                session,
                sub,
                user,
                TrafficAnomalyStatus.DISABLED,
                score,
                reasons,
                delta_bytes,
                delta_minutes,
                rate_mbps,
                floor_bytes,
                baseline_bytes,
                action,
            )
            if not dry_run:
                await self.marzban.modify_user(user.username, status="disabled")
                session.add(
                    AdminAuditLog(
                        admin_telegram_id=0,
                        action="traffic_anomaly_disable",
                        details=(
                            f"{user.username} score={score} delta={delta_bytes} "
                            f"minutes={delta_minutes} reasons={','.join(reasons)}"
                        )[:2000],
                    )
                )
            result = EvaluationResult(
                username=user.username,
                score=score,
                action=action,
                reasons=reasons,
                delta_bytes=delta_bytes,
                delta_minutes=delta_minutes,
                rate_mbps=rate_mbps,
                floor_bytes=floor_bytes,
                baseline_bytes=baseline_bytes,
                event_id=event.id,
            )
            if bot:
                await self._alert(bot, session, result, TrafficAnomalyStatus.DISABLED)
            return result

        event = await self._save_event(
            session,
            sub,
            user,
            TrafficAnomalyStatus.WATCH,
            score,
            reasons,
            delta_bytes,
            delta_minutes,
            rate_mbps,
            floor_bytes,
            baseline_bytes,
            "watch",
        )
        result = EvaluationResult(
            username=user.username,
            score=score,
            action="watch",
            reasons=reasons,
            delta_bytes=delta_bytes,
            delta_minutes=delta_minutes,
            rate_mbps=rate_mbps,
            floor_bytes=floor_bytes,
            baseline_bytes=baseline_bytes,
            event_id=event.id,
        )
        if bot:
            await self._alert(bot, session, result, TrafficAnomalyStatus.WATCH)
        return result

    async def run_guard(self, session: AsyncSession, bot: Bot) -> tuple[int, int, int]:
        if not self.settings.traffic_anomaly_enabled:
            return 0, 0, 0
        try:
            users, _ = await self.marzban.list_users(limit=500)
        except Exception as exc:
            logger.warning("traffic_anomaly_guard skipped: cannot list Marzban users: %s", exc)
            return 0, 0, 0
        usernames = [u.username for u in users]
        subs = (
            await session.scalars(
                select(Subscription).where(Subscription.marzban_username.in_(usernames))
            )
        ).all()
        sub_cache = {s.marzban_username: s for s in subs}
        snapshots = (
            await session.scalars(
                select(TrafficUsageSnapshot)
                .where(TrafficUsageSnapshot.marzban_username.in_(usernames))
                .order_by(
                    TrafficUsageSnapshot.marzban_username,
                    TrafficUsageSnapshot.checked_at.desc(),
                )
                .distinct(TrafficUsageSnapshot.marzban_username)
            )
        ).all()
        snapshot_cache = {s.marzban_username: s for s in snapshots}
        normal = 0
        watch = 0
        disabled = 0
        for user in users:
            try:
                outcome = await self.evaluate_user(
                    session,
                    user,
                    bot=bot,
                    dry_run=False,
                    sub_cache=sub_cache,
                    snapshot_cache=snapshot_cache,
                )
            except Exception as exc:
                logger.warning("traffic_anomaly user=%s failed: %s", user.username, exc)
                continue
            if not outcome:
                continue
            if outcome.action in ("normal", "cooldown"):
                normal += 1
            elif outcome.action in ("watch",):
                watch += 1
            else:
                disabled += 1
        return normal, watch, disabled

    async def reenable_with_note(
        self,
        session: AsyncSession,
        event_id: int,
        note: str,
        admin_id: int,
    ) -> TrafficAnomalyEvent | None:
        event = await session.get(TrafficAnomalyEvent, event_id)
        if not event:
            return None
        await self.marzban.modify_user(event.marzban_username, status="active")
        event.status = TrafficAnomalyStatus.FALSE_POSITIVE
        event.review_note = note[:2000]
        event.reviewed_by_admin_id = admin_id
        event.action_taken = "reenabled_by_admin"
        session.add(
            AdminAuditLog(
                admin_telegram_id=admin_id,
                action="traffic_anomaly_reenable",
                details=f"{event.marzban_username} event={event.id} note={note[:1800]}",
            )
        )
        return event

    async def cleanup_old_data(self, session: AsyncSession, days: int = 30) -> tuple[int, int]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        snap_res = await session.execute(
            delete(TrafficUsageSnapshot).where(TrafficUsageSnapshot.checked_at < cutoff)
        )
        event_res = await session.execute(
            delete(TrafficAnomalyEvent).where(TrafficAnomalyEvent.created_at < cutoff)
        )
        return int(snap_res.rowcount or 0), int(event_res.rowcount or 0)
