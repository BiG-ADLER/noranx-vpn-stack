import asyncio

from uvicorn import Config, Server
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent

from bot.config import get_settings
from bot.handlers import setup_routers
from bot.services.admin_commands import register_admin_bot_commands
from bot.services.registry import close_services, get_marzban
from bot.services.readiness import close_redis_client, wait_for_marzban
from bot.jobs.scheduler import setup_scheduler
from bot.middlewares.channel import StrictChannelMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.maintenance import MaintenanceMiddleware
from bot.middlewares.throttle import ThrottleMiddleware
from bot.middlewares.timing import TimingMiddleware
from bot.utils.logging import get_logger, setup_logging
from webhooks.app import app as webhook_app

logger = get_logger("main")
_bot_instance: Bot | None = None


def get_bot_instance() -> Bot | None:
    return _bot_instance


async def main() -> None:
    global _bot_instance
    setup_logging()
    settings = get_settings()

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required")

    if not settings.marzban_dry_run:
        await wait_for_marzban()

    storage = RedisStorage.from_url(settings.redis_url)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    _bot_instance = bot
    dp = Dispatcher(storage=storage)

    await register_admin_bot_commands(bot, settings)

    wh = await bot.get_webhook_info()
    if wh.url:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Removed stale Telegram webhook: %s", wh.url)

    @dp.errors.register
    async def ignore_stale_callback(event: ErrorEvent) -> bool:
        exc = event.exception
        if isinstance(exc, TelegramBadRequest):
            msg = (exc.message or "").lower()
            if "query is too old" in msg or "query id is invalid" in msg:
                return True
        return False

    dp.update.middleware(StrictChannelMiddleware())
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(TimingMiddleware())
    dp.update.middleware(ThrottleMiddleware())
    dp.update.middleware(MaintenanceMiddleware())
    dp.include_router(setup_routers())

    scheduler = setup_scheduler(bot)
    scheduler.start()

    webhook_config = Config(
        webhook_app,
        host=settings.webhook_host,
        port=settings.webhook_port,
        log_level="warning",
    )
    webhook_server = Server(webhook_config)
    logger.info("Webhook server on %s:%s", settings.webhook_host, settings.webhook_port)

    logger.info("Bot starting...")
    webhook_task = asyncio.create_task(webhook_server.serve())
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        webhook_server.should_exit = True
        await webhook_task
        await close_services()
        await close_redis_client()


if __name__ == "__main__":
    asyncio.run(main())
