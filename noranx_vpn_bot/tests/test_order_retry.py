from bot.services.order_retry import can_retry_order
from bot.db.models import OrderStatus


def test_can_retry_provisioning():
    class O:
        status = OrderStatus.PROVISIONING

    assert can_retry_order(O(), True)[0] is True


def test_cannot_retry_completed():
    class O:
        status = OrderStatus.COMPLETED

    assert can_retry_order(O(), True)[0] is False
