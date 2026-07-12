#!/usr/bin/env python3
"""Read-only Telegram bot health gate: token, polling, process, local HTTP."""

from __future__ import annotations

import asyncio
import subprocess
import sys

import httpx
from dotenv import dotenv_values


def _bot_processes() -> list[str]:
    out = subprocess.run(
        ["pgrep", "-af", "python -m bot.main"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip().splitlines()
    return [p for p in out if "pgrep" not in p]


async def main() -> int:
    cfg = dotenv_values(".env")
    token = (cfg.get("BOT_TOKEN") or "").strip()
    if not token:
        print("FAIL: BOT_TOKEN missing in .env")
        return 1

    fail = 0
    procs = _bot_processes()

    async with httpx.AsyncClient(timeout=15.0) as client:
        me = await client.get(f"https://api.telegram.org/bot{token}/getMe")
        mej = me.json()
        if mej.get("ok"):
            r = mej["result"]
            print(f"OK: getMe @{r.get('username')} ({r.get('first_name')})")
        else:
            print(f"FAIL: getMe — {mej.get('description')}")
            fail += 1

        wh = await client.get(f"https://api.telegram.org/bot{token}/getWebhookInfo")
        whj = wh.json().get("result", {})
        url = whj.get("url") or ""
        if url:
            print(f"WARN: webhook set ({url}) — bot expects polling mode")
        else:
            print("OK: webhook empty (polling mode)")

        if len(procs) == 1:
            print("OK: polling assumed (single bot process; skip getUpdates probe)")
        else:
            gu = await client.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"limit": 1, "timeout": 0},
            )
            guj = gu.json()
            if guj.get("ok"):
                print("OK: getUpdates (no conflict)")
            else:
                print(f"FAIL: getUpdates — {guj.get('description')}")
                fail += 1

        try:
            hr = await client.get("http://127.0.0.1:8080/health")
            if hr.status_code == 200 and "ok" in hr.text:
                print("OK: local /health")
            else:
                print(f"FAIL: local /health — {hr.status_code} {hr.text[:80]}")
                fail += 1
        except Exception as e:
            print(f"FAIL: local /health — {e}")
            fail += 1

    if len(procs) == 1:
        print(f"OK: single bot process ({procs[0].split()[0]})")
    elif len(procs) == 0:
        print("FAIL: no bot.main process")
        fail += 1
    else:
        print(f"FAIL: {len(procs)} bot.main processes (expected 1)")
        for p in procs:
            print(f"  {p}")
        fail += 1

    if subprocess.run(["systemctl", "is-active", "--quiet", "noranx-bot"], check=False).returncode == 0:
        print("OK: noranx-bot.service active")
    else:
        print("WARN: noranx-bot.service not active")

    print(f"=== failures={fail} ===")
    return fail


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
