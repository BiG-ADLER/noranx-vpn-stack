import json
import re
import time
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings, get_settings
from bot.db.models import Setting
from bot.services.readiness import get_redis_client
from bot.utils.logging import get_logger

logger = get_logger("exchange_rate")

CACHE_KEY = "fx:usd_irr"
SETTING_KEY = "fx_usd_irr_manual"


@dataclass
class RateSnapshot:
    irr_per_usd: int
    toman_per_usd: int
    source: str
    fetched_at: float

    @property
    def age_seconds(self) -> float:
        return time.time() - self.fetched_at


class ExchangeRateError(Exception):
    pass


def _parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    val = int(digits)
    if val < 100_000:
        return None
    return val


async def _fetch_tgju() -> int | None:
    url = "https://www.tgju.org/profile/price_dollar_rl"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NoranXBot/1.0)"}
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text
    patterns = [
        r'data-price="(\d+)"',
        r'"price_dollar_rl"\s*,\s*"p"\s*:\s*"([\d,]+)"',
        r'price_dollar_rl[^>]*>[\s\S]*?([\d,]{6,})',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            val = _parse_price(m.group(1))
            if val:
                return val
    return None


async def _fetch_nobitex() -> int | None:
    url = "https://api.nobitex.ir/v2/orderbook/USDTIRT"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    bids = data.get("bids") or []
    asks = data.get("asks") or []
    prices: list[int] = []
    for side in (bids, asks):
        if side and side[0]:
            try:
                prices.append(int(float(side[0][0])))
            except (ValueError, IndexError, TypeError):
                pass
    if not prices:
        return None
    return int(sum(prices) / len(prices))


async def _read_manual(session: AsyncSession | None) -> int | None:
    if session:
        row = await session.get(Setting, SETTING_KEY)
        if row and row.value.strip().isdigit():
            return int(row.value.strip())
    manual = get_settings().fx_usd_irr_manual
    return manual if manual > 0 else None


async def _cache_get(redis_url: str) -> RateSnapshot | None:
    try:
        r = await get_redis_client()
        raw = await r.get(CACHE_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        return RateSnapshot(
            irr_per_usd=int(data["irr_per_usd"]),
            toman_per_usd=int(data["toman_per_usd"]),
            source=data["source"],
            fetched_at=float(data["fetched_at"]),
        )
    except Exception as e:
        logger.debug("cache read failed: %s", e)
        return None


async def _cache_set(redis_url: str, snap: RateSnapshot) -> None:
    try:
        r = await get_redis_client()
        payload = json.dumps(
            {
                "irr_per_usd": snap.irr_per_usd,
                "toman_per_usd": snap.toman_per_usd,
                "source": snap.source,
                "fetched_at": snap.fetched_at,
            }
        )
        ttl = get_settings().fx_cache_ttl_seconds
        await r.setex(CACHE_KEY, ttl, payload)
    except Exception as e:
        logger.warning("cache write failed: %s", e)


async def set_manual_rate(session: AsyncSession, irr_per_usd: int) -> None:
    row = await session.get(Setting, SETTING_KEY)
    if row:
        row.value = str(irr_per_usd)
    else:
        session.add(Setting(key=SETTING_KEY, value=str(irr_per_usd)))
    await session.flush()
    snap = RateSnapshot(
        irr_per_usd=irr_per_usd,
        toman_per_usd=irr_per_usd // 10,
        source="manual",
        fetched_at=time.time(),
    )
    await _cache_set(get_settings().redis_url, snap)


class ExchangeRateService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def get_rate(self, session: AsyncSession | None = None) -> RateSnapshot:
        cached = await _cache_get(self._settings.redis_url)
        if cached and cached.age_seconds < self._settings.fx_cache_ttl_seconds:
            return cached

        irr: int | None = None
        source = self._settings.fx_source.lower()

        if source == "manual":
            irr = await _read_manual(session)
            src_label = "manual"
        else:
            fetchers = []
            if source == "tgju":
                fetchers = [("tgju", _fetch_tgju), ("nobitex", _fetch_nobitex)]
            elif source == "nobitex":
                fetchers = [("nobitex", _fetch_nobitex), ("tgju", _fetch_tgju)]
            else:
                fetchers = [("tgju", _fetch_tgju), ("nobitex", _fetch_nobitex)]

            src_label = "unknown"
            for name, fn in fetchers:
                try:
                    irr = await fn()
                    if irr:
                        src_label = name
                        break
                except Exception as e:
                    logger.warning("fx fetch %s failed: %s", name, e)

        if irr is None:
            irr = await _read_manual(session)
            if irr:
                src_label = "manual"

        if irr is None and cached:
            return cached

        if irr is None:
            raise ExchangeRateError("نرخ دلار در دسترس نیست. بعداً تلاش کنید.")

        snap = RateSnapshot(
            irr_per_usd=irr,
            toman_per_usd=irr // 10,
            source=src_label,
            fetched_at=time.time(),
        )
        await _cache_set(self._settings.redis_url, snap)
        return snap

    def usd_to_toman(self, usd: float, rate: RateSnapshot) -> int:
        return int(round(usd * rate.toman_per_usd))

    def usd_to_irr(self, usd: float, rate: RateSnapshot) -> int:
        return int(round(usd * rate.irr_per_usd))
