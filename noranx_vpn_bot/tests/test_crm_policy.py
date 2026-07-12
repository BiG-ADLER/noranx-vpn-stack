import pytest

from bot.db.models import TicketPriority, TicketStatus
from bot.services.admin_broadcast import (
    DirectUserBroadcastDisabledError,
    count_active_subscriber_users,
    send_broadcast,
)
from bot.services.plans import PlanValidationError, validate_plan_payload


@pytest.mark.asyncio
async def test_user_broadcast_disabled_policy():
    with pytest.raises(DirectUserBroadcastDisabledError):
        await send_broadcast(
            bot=None,  # type: ignore[arg-type]
            session=None,
            text="hello",
            photo_file_id=None,
            admin_telegram_id=1,
        )


@pytest.mark.asyncio
async def test_count_active_subscriber_users_disabled_mode():
    value = await count_active_subscriber_users(None)
    assert value == 0


def test_ticket_enums_include_crm_states():
    assert TicketStatus.IN_PROGRESS.value == "in_progress"
    assert TicketStatus.WAITING_USER.value == "waiting_user"
    assert TicketStatus.RESOLVED.value == "resolved"
    assert TicketPriority.URGENT.value == "urgent"


def test_plan_validation_bounds():
    validate_plan_payload(slug="device_9", name_fa="پلن تست", device_count=2, price_toman=50000)
    with pytest.raises(PlanValidationError):
        validate_plan_payload(slug="", name_fa="x", device_count=1, price_toman=1000)
