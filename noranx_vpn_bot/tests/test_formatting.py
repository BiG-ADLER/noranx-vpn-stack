from datetime import UTC, datetime, timedelta

from bot.utils.formatting import days_until_expiry, format_relative_time, traffic_progress_bar


def test_days_until_expiry_future():
    dt = datetime.now(UTC) + timedelta(days=5)
    assert days_until_expiry(dt) == 5


def test_days_until_expiry_none():
    assert days_until_expiry(None) is None


def test_traffic_progress_bar_unlimited():
    assert traffic_progress_bar(100, None) == "نامحدود"


def test_traffic_progress_bar_limited():
    bar = traffic_progress_bar(500, 1000)
    assert "█" in bar
    assert "%" in bar


def test_format_relative_time_minutes():
    dt = datetime.now(UTC) - timedelta(minutes=10)
    assert "دقیقه" in format_relative_time(dt)
