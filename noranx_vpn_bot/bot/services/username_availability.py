from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Subscription
from bot.services.marzban import MarzbanService
from bot.utils.username import normalize_marzban_username, validate_marzban_username


async def is_username_available(
    session: AsyncSession,
    marzban: MarzbanService,
    raw_name: str,
) -> tuple[bool, str | None, str | None]:
    """Returns (available, error_message, normalized_name)."""
    name = normalize_marzban_username(raw_name)
    err = validate_marzban_username(name)
    if err:
        return False, err, None

    existing = await session.scalar(
        select(Subscription.id).where(Subscription.marzban_username == name).limit(1)
    )
    if existing:
        return False, "این نام کاربری قبلاً استفاده شده است.", None

    mb_user = await marzban.get_user(name)
    if mb_user is not None:
        return False, "این نام کاربری در پنل موجود است.", None

    return True, None, name
