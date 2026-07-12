import pytest

from bot.services.admin_ops import OpsSnapshot, badge, format_ops_inbox_text, health_badge
from bot.services.order_retry import can_retry_order
from bot.db.models import OrderStatus


def test_badge_zero():
    assert badge(0) == ""


def test_badge_positive():
    assert badge(3) == " (3)"


def test_ops_snapshot_total_actionable():
    snap = OpsSnapshot(
        c2c_review=2,
        c2c_waiting=1,
        open_tickets=1,
        stuck_orders=1,
        failed_orders=0,
        limiter_drift=3,
        marzban_ok=True,
        ip_ok=False,
    )
    assert snap.total_actionable == 2 + 1 + 1 + 1 + 0 + 1 + 1


def test_format_ops_inbox_text():
    snap = OpsSnapshot(1, 0, 2, 0, 0, 0, True, True)
    text = format_ops_inbox_text(snap)
    assert "صندوق عملیات" in text
    assert health_badge(True) in text


def test_can_retry_order_failed_with_payment():
    class FakeOrder:
        status = OrderStatus.FAILED

    ok, msg = can_retry_order(FakeOrder(), True)
    assert ok is True


def test_can_retry_order_pending_no_payment():
    class FakeOrder:
        status = OrderStatus.FAILED

    ok, msg = can_retry_order(FakeOrder(), False)
    assert ok is False
