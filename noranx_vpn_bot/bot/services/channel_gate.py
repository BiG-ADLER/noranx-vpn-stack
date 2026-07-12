"""Channel membership gate helpers."""

from aiogram import Bot
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import get_settings
from bot.keyboards.channel_gate import channel_gate_kb
from bot.utils.logging import get_logger

logger = get_logger("channel_gate")

GATE_MESSAGE = (
    "برای استفاده از ربات ابتدا در کانال ما عضو شوید.\n"
    "پس از عضویت دکمه «بررسی عضویت» را بزنید."
)

_member_cache: dict[int, tuple[bool, float]] = {}


async def resolve_channel_link(bot: Bot) -> str:
    settings = get_settings()
    if settings.required_channel_link:
        return settings.required_channel_link
    if not settings.required_channel_id:
        return ""
    try:
        chat = await bot.get_chat(int(settings.required_channel_id))
        if chat.username:
            return f"https://t.me/{chat.username}"
        if chat.invite_link:
            return chat.invite_link
    except Exception:
        pass
    return ""


def is_exempt(user_id: int) -> bool:
    settings = get_settings()
    if not settings.required_channel_id:
        return True
    return user_id in settings.admin_ids


def _channel_id() -> int | None:
    settings = get_settings()
    if not settings.required_channel_id:
        return None
    return int(settings.required_channel_id)


async def is_channel_member(bot: Bot, user_id: int) -> bool:
    channel_id = _channel_id()
    if channel_id is None:
        return True

    settings = get_settings()
    cache_ttl = settings.channel_check_cache_seconds
    if cache_ttl > 0:
        import time

        cached = _member_cache.get(user_id)
        if cached is not None:
            ok, ts = cached
            if time.time() - ts < cache_ttl:
                return ok

    try:
        member = await bot.get_chat_member(channel_id, user_id)
        ok = member.status not in ("left", "kicked")
    except Exception as exc:
        logger.warning("channel_gate member_check_failed user_id=%s error=%s", user_id, exc)
        return False

    if cache_ttl > 0:
        import time

        _member_cache[user_id] = (ok, time.time())
    return ok


def invalidate_member_cache(user_id: int) -> None:
    _member_cache.pop(user_id, None)


async def send_gate_screen(
    bot: Bot,
    chat_id: int,
    *,
    edit_message: Message | None = None,
) -> None:
    link = await resolve_channel_link(bot)
    kb = channel_gate_kb(link)
    if edit_message:
        try:
            await edit_message.edit_text(GATE_MESSAGE, reply_markup=kb)
            return
        except Exception:
            pass
    await bot.send_message(chat_id, GATE_MESSAGE, reply_markup=kb)


def extract_user_id(event: TelegramObject) -> int | None:
    if isinstance(event, Message) and event.from_user:
        return event.from_user.id
    if isinstance(event, CallbackQuery) and event.from_user:
        return event.from_user.id
    return None


def is_start_command(event: TelegramObject) -> bool:
    if not isinstance(event, Message) or not event.text:
        return False
    return event.text.startswith("/start")


def is_recheck_callback(event: TelegramObject) -> bool:
    return isinstance(event, CallbackQuery) and event.data == "channel:recheck"
