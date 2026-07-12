from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bot.config import get_settings
from bot.db.models import TrafficAnomalyEvent, TrafficAnomalyStatus
from bot.services.traffic_anomaly import TrafficAnomalyService


class DummyMarzban:
    def __init__(self) -> None:
        self.modify_user = AsyncMock()


def test_traffic_anomaly_status_enum_values():
    assert TrafficAnomalyStatus.WATCH.value == "watch"
    assert TrafficAnomalyStatus.DISABLED.value == "disabled"
    assert TrafficAnomalyStatus.FALSE_POSITIVE.value == "false_positive"


def test_floor_scales_by_device_limit():
    settings = get_settings()
    svc = TrafficAnomalyService(settings, DummyMarzban())  # type: ignore[arg-type]
    assert svc._floor_for_device_limit(1) == settings.traffic_anomaly_floor_1_device_bytes
    assert svc._floor_for_device_limit(2) == settings.traffic_anomaly_floor_2_device_bytes
    assert svc._floor_for_device_limit(3) == settings.traffic_anomaly_floor_3p_device_bytes


@pytest.mark.asyncio
async def test_cleanup_old_data_reports_deleted_counts():
    settings = get_settings()
    svc = TrafficAnomalyService(settings, DummyMarzban())  # type: ignore[arg-type]
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(rowcount=3),
            SimpleNamespace(rowcount=5),
        ]
    )
    deleted_snapshots, deleted_events = await svc.cleanup_old_data(session, days=30)
    assert deleted_snapshots == 3
    assert deleted_events == 5
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_reenable_with_note_updates_event():
    marzban = DummyMarzban()
    settings = get_settings()
    svc = TrafficAnomalyService(settings, marzban)  # type: ignore[arg-type]
    session = AsyncMock()
    session.add = Mock()
    event = TrafficAnomalyEvent(
        id=11,
        subscription_id=1,
        marzban_username="testuser",
        status=TrafficAnomalyStatus.DISABLED,
        score=6,
    )
    session.get = AsyncMock(return_value=event)

    out = await svc.reenable_with_note(session, 11, "false positive check complete", 1001)
    assert out is not None
    assert out.status == TrafficAnomalyStatus.FALSE_POSITIVE
    assert out.reviewed_by_admin_id == 1001
    assert "false positive" in (out.review_note or "")
    marzban.modify_user.assert_awaited_once_with("testuser", status="active")
