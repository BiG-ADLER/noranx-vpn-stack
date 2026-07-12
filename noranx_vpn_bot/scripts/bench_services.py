#!/usr/bin/env python3
"""Benchmark hot service paths; writes JSON to logs/bench-*.json."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.config import get_settings
from bot.db.session import async_session_factory
from bot.services.admin_ops import build_ops_snapshot
from bot.services.registry import close_services, get_ip_limiter, get_marzban
from bot.services.readiness import close_redis_client


async def _bench_health(name: str, fn, iterations: int) -> dict:
    samples: list[int] = []
    errors: list[str] = []
    for _ in range(iterations):
        start = time.perf_counter()
        try:
            ok, msg, ms = await fn()
            samples.append(int(ms if ms is not None else (time.perf_counter() - start) * 1000))
            if not ok:
                errors.append(str(msg)[:120])
        except Exception as e:
            errors.append(str(e)[:120])
            samples.append(int((time.perf_counter() - start) * 1000))
    return {
        "name": name,
        "iterations": iterations,
        "ms_median": int(statistics.median(samples)) if samples else 0,
        "ms_p95": int(statistics.quantiles(samples, n=20)[-1]) if len(samples) >= 2 else (samples[0] if samples else 0),
        "errors": errors[:3],
    }


async def _bench_ops_snapshot(iterations: int) -> dict:
    samples: list[int] = []
    errors: list[str] = []
    for _ in range(iterations):
        start = time.perf_counter()
        try:
            async with async_session_factory() as session:
                await build_ops_snapshot(session)
            samples.append(int((time.perf_counter() - start) * 1000))
        except Exception as e:
            errors.append(str(e)[:120])
            samples.append(int((time.perf_counter() - start) * 1000))
    return {
        "name": "build_ops_snapshot",
        "iterations": iterations,
        "ms_median": int(statistics.median(samples)) if samples else 0,
        "ms_p95": int(statistics.quantiles(samples, n=20)[-1]) if len(samples) >= 2 else (samples[0] if samples else 0),
        "errors": errors[:3],
    }


async def run_bench(iterations: int) -> dict:
    get_settings()
    results = await asyncio.gather(
        _bench_health("marzban_health_check", get_marzban().health_check, iterations),
        _bench_health("ip_limiter_health_check", get_ip_limiter().health_check, iterations),
        _bench_ops_snapshot(iterations),
    )
    return {
        "ts": datetime.now(UTC).isoformat(),
        "iterations": iterations,
        "benchmarks": list(results),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark NoranX bot service paths")
    parser.add_argument("-n", "--iterations", type=int, default=3)
    args = parser.parse_args()
    payload = await run_bench(args.iterations)
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    out = log_dir / f"bench-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"Wrote {out}")
    await close_services()
    await close_redis_client()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
