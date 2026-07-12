#!/usr/bin/env python3
"""Smoke test Marzban + IP limiter integration."""

import argparse
import asyncio
import sys
import time

from bot.config import get_settings
from bot.services.ip_limiter import IpLimiterService
from bot.services.marzban import MarzbanService


async def run(
    plan_device_count: int,
    cleanup: bool,
    *,
    skip_provision: bool = False,
) -> int:
    settings = get_settings()
    marzban = MarzbanService(settings)
    ip_lim = IpLimiterService(settings)
    failed: list[str] = []

    print("=== Health Check ===")
    print(f"MARZBAN_URL={settings.marzban_url}")
    if settings.marzban_url.startswith("http://"):
        print("WARNING: MARZBAN_URL uses http:// — use https:// if Marzban has SSL enabled")

    for name, svc in [("Marzban", marzban), ("IP Limiter", ip_lim)]:
        ok, msg, ms = await svc.health_check()
        status = "OK" if ok else "FAIL"
        print(f"{name}: {status} ({ms}ms) — {msg}")
        if not ok:
            failed.append(name)
            if not settings.provision_skip_limiters and name != "Marzban":
                print(f"Warning: {name} unreachable (set PROVISION_SKIP_LIMITERS=true for dev)")

    if "Marzban" in failed:
        print("\n=== Marzban unreachable — skipping provision test ===")
        return 1

    if skip_provision:
        if failed:
            print(f"\n=== Failed: {', '.join(failed)} ===")
            return 1
        print("\n=== All checks passed (provision skipped) ===")
        return 0

    username = f"test_hc_{int(time.time()) % 100000}"
    expire = int(time.time()) + 3600
    subscription_url = ""
    print(f"\n=== Provision test user: {username} ===")
    try:
        user = await marzban.create_user(username, 0, expire, note="health_check")
        subscription_url = user.subscription_url or ""
        print(f"Marzban create: OK — {subscription_url}")
        if not settings.provision_skip_limiters:
            await ip_lim.set_limit(username, plan_device_count)
            print(f"IP limit: OK — {plan_device_count}")

            ip_lim_cfg = await ip_lim.get_limit(username)
            if not ip_lim_cfg or not ip_lim_cfg.get("configured"):
                print(f"IP get_limit drift: {ip_lim_cfg}")
                failed.append("ip_get_limit")
            elif int(ip_lim_cfg.get("limit", -1)) != plan_device_count:
                print(f"IP get_limit mismatch: {ip_lim_cfg}")
                failed.append("ip_get_limit")
            else:
                print(f"IP get_limit: OK — {ip_lim_cfg.get('limit')}")
        else:
            print("Limiters: SKIPPED (PROVISION_SKIP_LIMITERS=true)")
        fetched = await marzban.get_user(username)
        print(f"Fetch user: {fetched.status if fetched else 'FAIL'}")
    except Exception as e:
        print(f"FAIL: {e}")
        failed.append("provision")
    finally:
        if cleanup:
            try:
                if not settings.provision_skip_limiters:
                    await ip_lim.remove_limit(username)
                await marzban.delete_user(username)
                print("Cleanup: OK")
            except Exception as e:
                print(f"Cleanup warning: {e}")

    if failed:
        print(f"\n=== Failed: {', '.join(failed)} ===")
        return 1
    print("\n=== All checks passed ===")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", default="device_2", help="Plan slug hint for device count")
    parser.add_argument("--no-cleanup", action="store_true")
    parser.add_argument(
        "--skip-provision",
        action="store_true",
        help="Only run service health checks (no test user creation)",
    )
    args = parser.parse_args()
    device_count = 2
    if args.plan.endswith("_1"):
        device_count = 1
    elif args.plan.endswith("_3"):
        device_count = 3
    sys.exit(
        asyncio.run(
            run(
                device_count,
                cleanup=not args.no_cleanup,
                skip_provision=args.skip_provision,
            )
        )
    )


if __name__ == "__main__":
    main()
