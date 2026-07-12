"""FSM lifecycle tests for shop custom username flow."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Chat, Message, User

from bot.handlers.user import shop as shop_mod
from bot.handlers.user.shop import (
    CUSTOM_USERNAME_PROMPT,
    MARZBAN_UNAVAILABLE_MSG,
    shop_username_custom_apply,
)
from bot.services.marzban import MarzbanError


def _message(text: str, telegram_id: int = 111) -> MagicMock:
    user = User(id=telegram_id, is_bot=False, first_name="T")
    chat = Chat(id=telegram_id, type="private")
    msg = MagicMock(spec=Message)
    msg.message_id = 1
    msg.date = datetime.now(UTC)
    msg.chat = chat
    msg.from_user = user
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _order(plan_id: int = 1, user_id: int = 1) -> MagicMock:
    order = MagicMock()
    order.id = 42
    order.user_id = user_id
    order.plan_id = plan_id
    order.total_toman = 50000
    return order


def _user(user_id: int = 1, telegram_id: int = 111) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.telegram_id = telegram_id
    return user


def _plan() -> MagicMock:
    plan = MagicMock()
    plan.name_fa = "پلن تست"
    return plan


@pytest.mark.asyncio
async def test_invalid_username_keeps_fsm():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"order_id": 42})
    session = AsyncMock()
    session.get = AsyncMock(return_value=_order())
    session.scalar = AsyncMock(return_value=_user())
    message = _message("ab")

    await shop_username_custom_apply(message, state, session)

    state.clear.assert_not_awaited()
    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "❌" in text
    assert CUSTOM_USERNAME_PROMPT in text
    assert message.answer.await_args.kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_valid_username_clears_fsm():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"order_id": 42})
    session = AsyncMock()
    session.get = AsyncMock(side_effect=lambda model, pk: _order() if pk == 42 else _plan())
    session.scalar = AsyncMock(return_value=_user())
    session.flush = AsyncMock()
    message = _message("good_name1")

    with patch.object(
        shop_mod,
        "is_username_available",
        AsyncMock(return_value=(True, None, "good_name1")),
    ):
        await shop_username_custom_apply(message, state, session)

    state.clear.assert_awaited_once()
    assert message.answer.await_args.args[0].count("good_name1") >= 1


@pytest.mark.asyncio
async def test_taken_username_keeps_fsm():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"order_id": 42})
    session = AsyncMock()
    session.get = AsyncMock(return_value=_order())
    session.scalar = AsyncMock(return_value=_user())
    message = _message("taken_name")

    with patch.object(
        shop_mod,
        "is_username_available",
        AsyncMock(return_value=(False, "این نام کاربری قبلاً استفاده شده است.", None)),
    ):
        await shop_username_custom_apply(message, state, session)

    state.clear.assert_not_awaited()
    text = message.answer.await_args.args[0]
    assert "این نام کاربری قبلاً استفاده شده است." in text
    assert CUSTOM_USERNAME_PROMPT in text


@pytest.mark.asyncio
async def test_marzban_error_keeps_fsm():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"order_id": 42})
    session = AsyncMock()
    session.get = AsyncMock(return_value=_order())
    session.scalar = AsyncMock(return_value=_user())
    message = _message("good_name1")

    with patch.object(
        shop_mod,
        "is_username_available",
        AsyncMock(side_effect=MarzbanError("get_user", "connection refused")),
    ):
        await shop_username_custom_apply(message, state, session)

    state.clear.assert_not_awaited()
    text = message.answer.await_args.args[0]
    assert MARZBAN_UNAVAILABLE_MSG in text
    assert CUSTOM_USERNAME_PROMPT in text


@pytest.mark.asyncio
async def test_fatal_order_missing_clears_fsm():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"order_id": 99})
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.scalar = AsyncMock(return_value=_user())
    message = _message("good_name1")

    await shop_username_custom_apply(message, state, session)

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once_with("سفارش یافت نشد.")
