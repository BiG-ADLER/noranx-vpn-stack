from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat

from bot.config import Settings
from bot.services.admin_help_catalog import TELEGRAM_ADMIN_COMMANDS
from bot.utils.logging import get_logger

logger = get_logger("admin_commands")


async def register_admin_bot_commands(bot: Bot, settings: Settings) -> None:
    commands = [
        BotCommand(command=cmd, description=desc) for cmd, desc in TELEGRAM_ADMIN_COMMANDS
    ]
    for admin_id in settings.admin_ids:
        scope = BotCommandScopeChat(chat_id=admin_id)
        try:
            await bot.set_my_commands(commands, scope=scope)
            logger.info("Registered %d admin commands for %s", len(commands), admin_id)
        except Exception as e:
            logger.warning("Failed to set admin commands for %s: %s", admin_id, e)
