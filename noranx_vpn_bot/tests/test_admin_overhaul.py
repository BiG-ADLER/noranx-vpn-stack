"""Tests for admin overhaul services."""

import pytest
from unittest.mock import AsyncMock, Mock

from bot.services import bot_content
from bot.services.audience import AudienceSegment, count_segment


@pytest.mark.asyncio
async def test_bot_content_defaults():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    text = await bot_content.get_welcome_text(session)
    assert "NoranX" in text


@pytest.mark.asyncio
async def test_audience_count_all():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=5)
    n = await count_segment(session, AudienceSegment.ALL_STARTED)
    assert n == 5


def test_audience_segment_labels():
    assert AudienceSegment.ACTIVE_SUBSCRIBERS.value == "active_subscribers"
