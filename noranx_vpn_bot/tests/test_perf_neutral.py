from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient

from bot.middlewares.maintenance import MaintenanceMiddleware
from bot.services.admin_ops import OpsSnapshot, build_ops_snapshot
from bot.services.marzban import MarzbanService
from webhooks.app import app


@pytest.mark.asyncio
async def test_marzban_reuses_http_client():
    settings = MagicMock()
    settings.marzban_url = "https://example.com"
    settings.marzban_dry_run = True
    settings.marzban_verify_ssl = True
    svc = MarzbanService(settings)

    with patch("bot.services.marzban.httpx.AsyncClient") as client_cls:
        client = AsyncMock(spec=AsyncClient)
        client_cls.return_value = client
        c1 = await svc._get_client()
        c2 = await svc._get_client()
        assert c1 is c2
        client_cls.assert_called_once()
        await svc.aclose()


@pytest.mark.asyncio
async def test_maintenance_middleware_uses_injected_session():
    mw = MaintenanceMiddleware()
    session = AsyncMock()
    handler = AsyncMock(return_value="ok")

    with patch("bot.middlewares.maintenance.bot_content.is_maintenance_mode", AsyncMock(return_value=False)):
        result = await mw(handler, MagicMock(), {"session": session})

    assert result == "ok"
    handler.assert_awaited_once()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_build_ops_snapshot_field_types():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(one=MagicMock(return_value=(0, 0, 0, 0, 0))))
    with (
        patch("bot.services.admin_ops.get_marzban") as gm,
        patch("bot.services.admin_ops.get_ip_limiter") as gi,
        patch("bot.services.admin_ops.get_sync_service") as gs,
    ):
        gm.return_value.health_check = AsyncMock(return_value=(True, "OK", 1))
        gi.return_value.health_check = AsyncMock(return_value=(True, "OK", 1))
        gs.return_value.count_limiter_drift = AsyncMock(return_value=0)
        snap = await build_ops_snapshot(session)

    assert isinstance(snap, OpsSnapshot)
    assert isinstance(snap.c2c_review, int)
    assert isinstance(snap.marzban_ok, bool)


def test_health_endpoint_unchanged():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_endpoint_schema():
    payload = {
        "status": "ok",
        "checks": {
            "postgres": {"ok": True, "ms": 2},
            "redis": {"ok": True, "ms": 1},
            "marzban": {"ok": True, "ms": 10},
            "ip_limiter": {"ok": True, "ms": 4},
        },
        "ts": "2026-06-16T12:00:00+00:00",
    }
    with patch("bot.services.readiness.run_readiness_checks", AsyncMock(return_value=payload)):
        client = TestClient(app)
        resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded", "fail")
    assert "checks" in data
    assert "ts" in data
    for key in ("postgres", "redis", "marzban", "ip_limiter"):
        assert key in data["checks"]
        assert "ok" in data["checks"][key]
        assert "ms" in data["checks"][key]
