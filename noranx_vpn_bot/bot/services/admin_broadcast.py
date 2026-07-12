from aiogram import Bot


class DirectUserBroadcastDisabledError(RuntimeError):
    pass


async def count_active_subscriber_users(session) -> int:
    return 0


async def send_broadcast(
    bot: Bot,
    session,
    *,
    text: str,
    photo_file_id: str | None,
    admin_telegram_id: int,
    progress_message=None,
) -> tuple[int, int]:
    raise DirectUserBroadcastDisabledError(
        "Direct user broadcast is disabled by policy. Use channel announcements only."
    )


async def send_broadcast_v2(
    bot: Bot,
    session,
    *,
    text: str,
    photo_file_id: str | None,
    admin_telegram_id: int,
    segment=None,
    single_telegram_id: int | None = None,
    progress_message=None,
) -> tuple[int, int]:
    raise DirectUserBroadcastDisabledError(
        "Direct user broadcast is disabled by policy. Use channel announcements only."
    )
