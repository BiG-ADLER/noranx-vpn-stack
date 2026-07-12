"""Tests for subscription delivery."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.utils.subscription_delivery import format_manual_configs_message


def test_format_manual_configs_message():
    text = format_manual_configs_message(["vless://uuid@host:443"])
    assert "VLESS" in text
    assert "vless://" in text


@pytest.mark.asyncio
async def test_subscription_delivery_no_plain_url_in_message():
    from bot.utils.subscription_delivery import send_subscription_details

    bot = AsyncMock()
    marzban = AsyncMock()
    marzban.get_user = AsyncMock(return_value=None)

    with patch(
        "bot.utils.subscription_delivery.make_qr_png_bytes", return_value=b"qr"
    ):
        await send_subscription_details(
            bot,
            123,
            marzban_username="test_user",
            subscription_url="https://sub.example.com/sub/token123",
            device_limit=1,
            marzban=marzban,
            settings=MagicMock(),
        )

    text_messages = [
        c.args[1] if c.args else c.kwargs.get("text", "")
        for c in bot.send_message.call_args_list
    ]
    combined = "\n".join(text_messages)
    assert "https://sub.example.com" not in combined
    assert "test_user" in combined
    bot.send_document.assert_awaited_once()
    doc_content = bot.send_document.await_args.args[1]
    assert b"/sub/token123" in doc_content.data
