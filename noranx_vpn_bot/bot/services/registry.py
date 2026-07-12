"""App-scoped service singletons for connection reuse."""

from bot.config import get_settings
from bot.services.ip_limiter import IpLimiterService
from bot.services.marzban import MarzbanService
from bot.services.sync import SyncService

_marzban: MarzbanService | None = None
_ip_limiter: IpLimiterService | None = None
_sync_service: SyncService | None = None


def get_marzban() -> MarzbanService:
    global _marzban
    if _marzban is None:
        _marzban = MarzbanService(get_settings())
    return _marzban


def get_ip_limiter() -> IpLimiterService:
    global _ip_limiter
    if _ip_limiter is None:
        _ip_limiter = IpLimiterService(get_settings())
    return _ip_limiter


def get_sync_service() -> SyncService:
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService(get_marzban(), get_ip_limiter())
    return _sync_service


async def close_services() -> None:
    global _marzban, _ip_limiter, _sync_service
    for svc in (_marzban, _ip_limiter):
        if svc is not None:
            await svc.aclose()
    _marzban = None
    _ip_limiter = None
    _sync_service = None
