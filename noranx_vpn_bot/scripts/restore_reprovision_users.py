#!/usr/bin/env python3
"""Re-provision bot subscriptions missing from Marzban after restore."""
from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from bot.config import get_settings
from bot.db.models import Subscription, SubscriptionStatus
from bot.db.session import async_session_factory
from bot.services.ip_limiter import IpLimiterService
from bot.services.marzban import MarzbanService
from bot.utils.logging import setup_logging
from bot.utils.subscription_url import normalize_subscription_url


async def main() -> int:
    setup_logging()
    settings = get_settings()
    marzban = MarzbanService(settings)
    ip_lim = IpLimiterService(settings)
    log_path = ROOT / "logs" / f"restore-reprovision-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    failures = 0

    async with async_session_factory() as session:
        subs = (
            await session.scalars(
                select(Subscription).where(
                    Subscription.status.in_(
                        [SubscriptionStatus.ACTIVE, SubscriptionStatus.DISABLED, SubscriptionStatus.LIMITED]
                    )
                )
            )
        ).all()

        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"reprovision subs={len(subs)}\n")
            for sub in subs:
                line_prefix = f"{sub.marzban_username}"
                existing = await marzban.get_user(sub.marzban_username)
                if existing:
                    msg = f"OK exists status={existing.status} url={existing.subscription_url}"
                    log.write(f"{line_prefix}: {msg}\n")
                    print(f"{line_prefix}: {msg}")
                    if existing.subscription_url:
                        sub.subscription_url = normalize_subscription_url(existing.subscription_url)
                else:
                    expire_ts = int(sub.expires_at.timestamp()) if sub.expires_at else 0
                    data_limit = int(sub.data_limit_bytes or 0)
                    try:
                        created = await marzban.create_user(
                            sub.marzban_username,
                            data_limit=data_limit,
                            expire_timestamp=expire_ts,
                            note=f"restore-reprovision sub_id={sub.id}",
                        )
                        await ip_lim.set_limit(sub.marzban_username, sub.ip_limit)
                        sub.subscription_url = normalize_subscription_url(created.subscription_url)
                        sub.status = SubscriptionStatus.ACTIVE
                        msg = f"CREATED url={sub.subscription_url}"
                        log.write(f"{line_prefix}: {msg}\n")
                        print(f"{line_prefix}: {msg}")
                    except Exception as e:
                        failures += 1
                        sub.status = SubscriptionStatus.PROVISIONING_FAILED
                        msg = f"FAIL {e}"
                        log.write(f"{line_prefix}: {msg}\n")
                        print(f"{line_prefix}: {msg}")
                await session.flush()
            await session.commit()
            log.write(f"failures={failures}\n")

    print(f"Log: {log_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
