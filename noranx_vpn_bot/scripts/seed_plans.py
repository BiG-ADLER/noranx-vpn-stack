"""Seed default plans and recharge packages."""

import asyncio

from sqlalchemy import select

from bot.db.models import Plan, RechargePackage
from bot.db.session import async_session_factory


PLANS = [
    {"slug": "device_1", "name_fa": "۱ دستگاه — ۱ ماهه", "device_count": 1, "price_toman": 250_000},
    {"slug": "device_2", "name_fa": "۲ دستگاه — ۱ ماهه", "device_count": 2, "price_toman": 275_000},
    {"slug": "device_3", "name_fa": "۳ دستگاه — ۱ ماهه", "device_count": 3, "price_toman": 300_000},
]

PACKAGES = [100_000, 250_000, 500_000, 1_000_000]


async def main() -> None:
    async with async_session_factory() as session:
        for i, p in enumerate(PLANS):
            existing = await session.scalar(select(Plan).where(Plan.slug == p["slug"]))
            if not existing:
                session.add(Plan(**p, duration_days=30))
        for i, amount in enumerate(PACKAGES):
            existing = await session.scalar(
                select(RechargePackage).where(RechargePackage.amount_toman == amount)
            )
            if not existing:
                session.add(RechargePackage(amount_toman=amount, sort_order=i))
        await session.commit()
    print("Seeded plans and recharge packages.")


if __name__ == "__main__":
    asyncio.run(main())
