"""Dependency readiness probes for /ready and admin debug."""

import asyncio
import time
from datetime import UTC, datetime

import redis.asyncio as aioredis
from sqlalchemy import text

from bot.config import get_settings
from bot.db.session import async_session_factory
from bot.services.registry import get_ip_limiter, get_marzban

_redis: aioredis.Redis | None = None


async def get_redis_client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def close_redis_client() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def run_readiness_checks() -> dict:
    checks: dict[str, dict] = {}

    async def _postgres() -> None:
        start = time.perf_counter()
        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            ms = int((time.perf_counter() - start) * 1000)
            checks["postgres"] = {"ok": True, "ms": ms}
        except Exception as e:
            ms = int((time.perf_counter() - start) * 1000)
            checks["postgres"] = {"ok": False, "ms": ms, "detail": str(e)[:200]}

    async def _redis() -> None:
        start = time.perf_counter()
        try:
            r = await get_redis_client()
            await r.ping()
            ms = int((time.perf_counter() - start) * 1000)
            checks["redis"] = {"ok": True, "ms": ms}
        except Exception as e:
            ms = int((time.perf_counter() - start) * 1000)
            checks["redis"] = {"ok": False, "ms": ms, "detail": str(e)[:200]}

    async def _service(name: str, health_fn) -> None:
        start = time.perf_counter()
        try:
            ok, msg, svc_ms = await health_fn()
            checks[name] = {"ok": ok, "ms": svc_ms or int((time.perf_counter() - start) * 1000)}
            if not ok and msg:
                checks[name]["detail"] = str(msg)[:200]
        except Exception as e:
            ms = int((time.perf_counter() - start) * 1000)
            checks[name] = {"ok": False, "ms": ms, "detail": str(e)[:200]}

    await asyncio.gather(
        _postgres(),
        _redis(),
        _service("marzban", get_marzban().health_check),
        _service("ip_limiter", get_ip_limiter().health_check),
    )

    all_ok = all(c.get("ok") for c in checks.values())
    any_ok = any(c.get("ok") for c in checks.values())
    if all_ok:
        status = "ok"
    elif any_ok:
        status = "degraded"
    else:
        status = "fail"

    return {
        "status": status,
        "checks": checks,
        "ts": datetime.now(UTC).isoformat(),
    }


def format_readiness_summary(payload: dict) -> str:
    lines = [f"GET /ready — {payload.get('status', '?')}"]
    for name, check in sorted((payload.get("checks") or {}).items()):
        ok = check.get("ok")
        ms = check.get("ms", "?")
        mark = "OK" if ok else "FAIL"
        lines.append(f"  {name}: {mark} ({ms}ms)")
    return "\n".join(lines)


async def wait_for_marzban(timeout_sec: int = 120, interval: float = 2.0) -> bool:
    """Block until Marzban responds or timeout (used at startup after host reboot)."""
    from bot.utils.logging import get_logger

    log = get_logger("readiness")
    settings = get_settings()
    if settings.marzban_dry_run:
        return True

    import time

    deadline = time.monotonic() + timeout_sec
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        ok, msg, _ = await get_marzban().health_check()
        if ok:
            log.info("Marzban ready after %s attempt(s): %s", attempt, msg)
            return True
        log.warning("Marzban not ready (attempt %s): %s", attempt, msg)
        await asyncio.sleep(interval)
    log.error("Marzban unavailable after %ss — scheduler jobs may skip Marzban work", timeout_sec)
    return False
