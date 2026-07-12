"""Guide CMS — load from DB with static fallback."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.db.models import AdminAuditLog, GuideApp, GuidePlatform, GuideStep
from bot.services import connect_guide as static


async def list_platforms(session: AsyncSession, *, active_only: bool = True) -> list[GuidePlatform]:
    q = select(GuidePlatform).order_by(GuidePlatform.sort_order)
    if active_only:
        q = q.where(GuidePlatform.is_active.is_(True))
    return list((await session.scalars(q)).all())


async def get_platform(session: AsyncSession, platform_id: int) -> GuidePlatform | None:
    return await session.get(GuidePlatform, platform_id)


async def get_platform_by_slug(session: AsyncSession, slug: str) -> GuidePlatform | None:
    return await session.scalar(select(GuidePlatform).where(GuidePlatform.slug == slug))


async def list_apps_for_platform(
    session: AsyncSession, platform_id: int, *, active_only: bool = True
) -> list[GuideApp]:
    q = (
        select(GuideApp)
        .where(GuideApp.platform_id == platform_id)
        .options(selectinload(GuideApp.steps))
        .order_by(GuideApp.sort_order)
    )
    if active_only:
        q = q.where(GuideApp.is_active.is_(True))
    return list((await session.scalars(q)).all())


async def get_app(session: AsyncSession, app_id: int) -> GuideApp | None:
    return await session.scalar(
        select(GuideApp).where(GuideApp.id == app_id).options(selectinload(GuideApp.steps))
    )


async def get_app_by_slug(session: AsyncSession, platform_slug: str, app_slug: str) -> GuideApp | None:
    platform = await get_platform_by_slug(session, platform_slug)
    if not platform:
        return None
    return await session.scalar(
        select(GuideApp)
        .where(GuideApp.platform_id == platform.id, GuideApp.slug == app_slug)
        .options(selectinload(GuideApp.steps))
    )


async def find_app_by_slug_global(session: AsyncSession, app_slug: str) -> tuple[GuideApp, GuidePlatform] | None:
    row = await session.scalar(
        select(GuideApp)
        .where(GuideApp.slug == app_slug, GuideApp.is_active.is_(True))
        .options(selectinload(GuideApp.steps), selectinload(GuideApp.platform))
        .limit(1)
    )
    if not row:
        return None
    return row, row.platform


def format_app_from_db(app: GuideApp) -> str:
    lines = [f"<b>📖 {app.title_fa}</b>\n"]
    for step in sorted(app.steps, key=lambda s: s.step_no):
        lines.append(f"{step.step_no}. {step.body_fa}")
    if app.extra_tip:
        lines.append(f"\n💡 {app.extra_tip}")
    return "\n".join(lines)


def format_platform_title(platform: GuidePlatform) -> str:
    return f"<b>📖 راهنما — {platform.title_fa}</b>\n\nاپ مورد نظر را انتخاب کنید:"


async def format_app_guide(session: AsyncSession, app_slug: str, platform_slug: str | None = None) -> str:
    if platform_slug:
        app = await get_app_by_slug(session, platform_slug, app_slug)
    else:
        found = await find_app_by_slug_global(session, app_slug)
        app = found[0] if found else None
    if app and app.steps:
        return format_app_from_db(app)
    if app_slug in static.APPS:
        return static.format_app_guide(app_slug)
    return "راهنما یافت نشد."


async def format_platform_menu(session: AsyncSession, platform_slug: str) -> str:
    platform = await get_platform_by_slug(session, platform_slug)
    if platform:
        return format_platform_title(platform)
    return static.format_platform_menu(platform_slug)


async def audit_guide(
    session: AsyncSession, admin_id: int, action: str, details: str
) -> None:
    session.add(
        AdminAuditLog(admin_telegram_id=admin_id, action=action, details=details)
    )
