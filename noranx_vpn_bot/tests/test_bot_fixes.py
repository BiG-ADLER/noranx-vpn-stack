"""Tests for bot fix regressions: debug import, admin scope, logging, payments."""

import logging
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.types import BotCommandScopeChat

from bot.db.models import Payment, PaymentStatus
from bot.services.admin_commands import register_admin_bot_commands
from bot.services.payment.completion import complete_payment
from bot.utils.logging import setup_logging


def test_debug_module_imports_sync_service():
    from bot.handlers.admin import debug as debug_mod

    assert hasattr(debug_mod, "get_sync_service")
    assert hasattr(debug_mod, "build_debug_report")


def test_setup_logging_idempotent():
    setup_logging()
    root = logging.getLogger()
    count_after_first = len(root.handlers)
    setup_logging()
    assert len(root.handlers) == count_after_first
    assert count_after_first == 2


@pytest.mark.asyncio
async def test_admin_commands_use_chat_scope():
    bot = AsyncMock()
    settings = Mock()
    settings.admin_ids = [12345]

    await register_admin_bot_commands(bot, settings)

    assert bot.set_my_commands.await_count == 1
    scope = bot.set_my_commands.await_args.kwargs["scope"]
    assert isinstance(scope, BotCommandScopeChat)
    assert scope.chat_id == 12345


@pytest.mark.asyncio
async def test_complete_payment_idempotent_completed():
    payment = Payment(
        id=1,
        user_id=1,
        provider="c2c",
        external_id="x",
        amount_toman=1000,
        status=PaymentStatus.COMPLETED,
    )
    session = AsyncMock()
    order_service = AsyncMock()

    result = await complete_payment(
        session,
        payment,
        order_service=order_service,
        source="test",
    )

    assert result.already_completed is True
    order_service.fulfill_order.assert_not_called()
