"""VPN plan CRUD."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminAuditLog, Plan


class PlanValidationError(ValueError):
    pass


def validate_plan_payload(*, slug: str, name_fa: str, device_count: int, price_toman: int) -> None:
    if not slug or len(slug) > 32:
        raise PlanValidationError("slug نامعتبر است.")
    if not name_fa or len(name_fa) > 128:
        raise PlanValidationError("نام فارسی نامعتبر است.")
    if device_count < 1 or device_count > 20:
        raise PlanValidationError("تعداد دستگاه باید بین 1 تا 20 باشد.")
    if price_toman < 1000 or price_toman > 100_000_000:
        raise PlanValidationError("قیمت خارج از محدوده مجاز است.")


async def list_plans(session: AsyncSession, *, active_only: bool = False) -> list[Plan]:
    q = select(Plan).order_by(Plan.sort_order, Plan.id)
    if active_only:
        q = q.where(Plan.is_active.is_(True))
    return list((await session.scalars(q)).all())


async def get_plan(session: AsyncSession, plan_id: int) -> Plan | None:
    return await session.get(Plan, plan_id)


async def get_plan_by_slug(session: AsyncSession, slug: str) -> Plan | None:
    return await session.scalar(select(Plan).where(Plan.slug == slug))


async def create_plan(
    session: AsyncSession,
    *,
    slug: str,
    name_fa: str,
    device_count: int,
    price_toman: int,
    duration_days: int = 30,
    admin_telegram_id: int,
) -> Plan:
    validate_plan_payload(
        slug=slug,
        name_fa=name_fa,
        device_count=device_count,
        price_toman=price_toman,
    )
    existing = await get_plan_by_slug(session, slug)
    if existing:
        raise PlanValidationError("slug تکراری است.")
    max_sort = await session.scalar(select(func.max(Plan.sort_order))) or 0
    plan = Plan(
        slug=slug,
        name_fa=name_fa,
        device_count=device_count,
        price_toman=price_toman,
        duration_days=duration_days,
        sort_order=max_sort + 1,
        is_active=True,
    )
    session.add(plan)
    session.add(
        AdminAuditLog(
            admin_telegram_id=admin_telegram_id,
            action="plan_create",
            details=f"slug={slug} price={price_toman}",
        )
    )
    await session.flush()
    return plan


async def update_plan_field(
    session: AsyncSession,
    plan: Plan,
    field: str,
    value,
    admin_telegram_id: int,
) -> None:
    if field == "name_fa":
        validate_plan_payload(
            slug=plan.slug,
            name_fa=str(value),
            device_count=plan.device_count,
            price_toman=plan.price_toman,
        )
    elif field == "price_toman":
        validate_plan_payload(
            slug=plan.slug,
            name_fa=plan.name_fa,
            device_count=plan.device_count,
            price_toman=int(value),
        )
    elif field == "device_count":
        validate_plan_payload(
            slug=plan.slug,
            name_fa=plan.name_fa,
            device_count=int(value),
            price_toman=plan.price_toman,
        )
    setattr(plan, field, value)
    session.add(
        AdminAuditLog(
            admin_telegram_id=admin_telegram_id,
            action="plan_update",
            details=f"id={plan.id} {field}={value}",
        )
    )


async def swap_sort_order(session: AsyncSession, plan: Plan, direction: str) -> bool:
    if direction == "up":
        neighbor = await session.scalar(
            select(Plan)
            .where(Plan.sort_order < plan.sort_order)
            .order_by(Plan.sort_order.desc())
            .limit(1)
        )
    else:
        neighbor = await session.scalar(
            select(Plan)
            .where(Plan.sort_order > plan.sort_order)
            .order_by(Plan.sort_order.asc())
            .limit(1)
        )
    if not neighbor:
        return False
    plan.sort_order, neighbor.sort_order = neighbor.sort_order, plan.sort_order
    return True
