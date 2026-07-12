"""User audience segments for directory and messaging."""

import enum
from dataclasses import dataclass

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.db.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    TelegramUser,
)


class AudienceSegment(str, enum.Enum):
    ALL_STARTED = "all_started"
    NEVER_PURCHASED = "never_purchased"
    ACTIVE_SUBSCRIBERS = "active_subscribers"
    EXPIRED = "expired"
    TRIAL_ONLY = "trial_only"
    BANNED = "banned"
    WALLET_POSITIVE = "wallet_balance_positive"
    HAS_PURCHASED = "has_purchased"
    SINGLE_USER = "single_user"


SEGMENT_LABELS = {
    AudienceSegment.ALL_STARTED: "همه کاربران",
    AudienceSegment.NEVER_PURCHASED: "بدون خرید",
    AudienceSegment.ACTIVE_SUBSCRIBERS: "اشتراک فعال",
    AudienceSegment.EXPIRED: "منقضی شده",
    AudienceSegment.TRIAL_ONLY: "فقط تست",
    AudienceSegment.BANNED: "مسدود",
    AudienceSegment.WALLET_POSITIVE: "موجودی کیف پول",
    AudienceSegment.HAS_PURCHASED: "خرید کرده",
    AudienceSegment.SINGLE_USER: "یک کاربر",
}


@dataclass
class UserRow:
    user: TelegramUser
    badge: str = ""


def _active_sub_exists():
    return exists(
        select(Subscription.id).where(
            Subscription.user_id == TelegramUser.id,
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.LIMITED]),
        )
    )


def _paid_order_exists():
    return exists(
        select(Order.id).where(
            Order.user_id == TelegramUser.id,
            Order.status == OrderStatus.COMPLETED,
        )
    )


def _completed_payment_exists():
    return exists(
        select(Payment.id).where(
            Payment.user_id == TelegramUser.id,
            Payment.status == PaymentStatus.COMPLETED,
            Payment.order_id.isnot(None),
        )
    )


def _segment_filter(segment: AudienceSegment, single_telegram_id: int | None = None):
    if segment == AudienceSegment.SINGLE_USER:
        if not single_telegram_id:
            return TelegramUser.id == -1
        return TelegramUser.telegram_id == single_telegram_id

    if segment == AudienceSegment.BANNED:
        return TelegramUser.is_banned.is_(True)

    base = TelegramUser.is_banned.is_(False)

    if segment == AudienceSegment.ALL_STARTED:
        return base
    if segment == AudienceSegment.NEVER_PURCHASED:
        return and_(base, ~_completed_payment_exists(), ~_active_sub_exists())
    if segment == AudienceSegment.ACTIVE_SUBSCRIBERS:
        return and_(base, _active_sub_exists())
    if segment == AudienceSegment.EXPIRED:
        return and_(
            base,
            ~_active_sub_exists(),
            exists(
                select(Subscription.id).where(
                    Subscription.user_id == TelegramUser.id,
                    Subscription.status == SubscriptionStatus.EXPIRED,
                )
            ),
        )
    if segment == AudienceSegment.TRIAL_ONLY:
        return and_(
            base,
            exists(
                select(Subscription.id).where(
                    Subscription.user_id == TelegramUser.id,
                    Subscription.is_trial.is_(True),
                    Subscription.status.in_(
                        [SubscriptionStatus.ACTIVE, SubscriptionStatus.LIMITED]
                    ),
                )
            ),
            ~_completed_payment_exists(),
        )
    if segment == AudienceSegment.WALLET_POSITIVE:
        return and_(base, TelegramUser.wallet_balance_toman > 0)
    if segment == AudienceSegment.HAS_PURCHASED:
        return and_(base, or_(_completed_payment_exists(), _paid_order_exists()))
    return base


async def count_segment(
    session: AsyncSession,
    segment: AudienceSegment,
    *,
    single_telegram_id: int | None = None,
) -> int:
    q = select(func.count()).select_from(TelegramUser).where(
        _segment_filter(segment, single_telegram_id)
    )
    return (await session.scalar(q)) or 0


async def list_users(
    session: AsyncSession,
    segment: AudienceSegment,
    *,
    page: int = 0,
    page_size: int = 15,
    sort: str = "newest",
    single_telegram_id: int | None = None,
) -> tuple[list[TelegramUser], int]:
    filt = _segment_filter(segment, single_telegram_id)
    total = (await session.scalar(select(func.count()).select_from(TelegramUser).where(filt))) or 0
    if sort == "oldest":
        order = TelegramUser.created_at.asc()
    elif sort == "wallet":
        order = TelegramUser.wallet_balance_toman.desc()
    else:
        order = TelegramUser.created_at.desc()
    rows = (
        await session.scalars(
            select(TelegramUser)
            .where(filt)
            .order_by(order, TelegramUser.id.desc())
            .offset(page * page_size)
            .limit(page_size)
        )
    ).all()
    return list(rows), total


async def resolve_telegram_ids(
    session: AsyncSession,
    segment: AudienceSegment,
    *,
    single_telegram_id: int | None = None,
) -> list[int]:
    filt = _segment_filter(segment, single_telegram_id)
    rows = await session.scalars(select(TelegramUser.telegram_id).where(filt))
    return list(rows.all())


async def user_badge(session: AsyncSession, user_id: int) -> str:
    badges = await user_badges_batch(session, [user_id])
    return badges.get(user_id, "👤")


async def user_badges_batch(session: AsyncSession, user_ids: list[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    active_ids = set(
        await session.scalars(
            select(Subscription.user_id)
            .where(
                Subscription.user_id.in_(user_ids),
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.LIMITED]),
            )
            .distinct()
        )
    )
    expired_ids = set(
        await session.scalars(
            select(Subscription.user_id)
            .where(
                Subscription.user_id.in_(user_ids),
                Subscription.status == SubscriptionStatus.EXPIRED,
            )
            .distinct()
        )
    )
    paid_ids = set(
        await session.scalars(
            select(Payment.user_id)
            .where(
                Payment.user_id.in_(user_ids),
                Payment.status == PaymentStatus.COMPLETED,
                Payment.order_id.isnot(None),
            )
            .distinct()
        )
    )
    result: dict[int, str] = {}
    for uid in user_ids:
        if uid in active_ids:
            result[uid] = "✅"
        elif uid in expired_ids:
            result[uid] = "⏰"
        elif uid in paid_ids:
            result[uid] = "🛒"
        else:
            result[uid] = "👤"
    return result
