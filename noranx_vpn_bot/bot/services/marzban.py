import time
from dataclasses import dataclass
from typing import Any

import httpx

from bot.config import Settings
from bot.utils.logging import get_logger
from bot.utils.subscription_url import normalize_subscription_url

logger = get_logger("marzban")

_INBOUND_CACHE: dict[str, Any] = {"at": 0.0, "proxies": {}, "inbounds": {}}
_INBOUND_TTL = 300.0


@dataclass
class MarzbanUser:
    username: str
    subscription_url: str | None
    expire: int
    data_limit: int
    status: str
    used_traffic: int = 0
    note: str = ""
    links: list[str] | None = None


@dataclass
class MarzbanUserListItem:
    username: str
    status: str
    used_traffic: int
    data_limit: int
    expire: int
    note: str = ""


class MarzbanError(Exception):
    def __init__(self, step: str, message: str) -> None:
        self.step = step
        super().__init__(f"{step}: {message}")


def _format_marzban_error(step: str, exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        body = exc.response.text[:200] if exc.response else ""
        return f"{step} failed (HTTP {exc.response.status_code}): {body or exc}"
    if isinstance(exc, httpx.RemoteProtocolError):
        return (
            f"{step} failed: server disconnected — Marzban likely requires HTTPS "
            f"(set MARZBAN_URL=https://127.0.0.1:8000)"
        )
    if isinstance(exc, httpx.ConnectError):
        return f"{step} failed: cannot connect to Marzban at configured URL"
    return f"{step} failed: {exc}"


_SUPPORTED_PROTOCOLS = ("vless", "vmess", "trojan", "shadowsocks")


def _excluded_inbound_prefixes(settings: Settings | None = None) -> tuple[str, ...]:
    from bot.config import get_settings

    settings = settings or get_settings()
    raw = (settings.marzban_excluded_inbound_prefixes or "").strip()
    if not raw:
        return ()
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def _filter_inbound_tags(tags: list[str], settings: Settings | None = None) -> list[str]:
    prefixes = _excluded_inbound_prefixes(settings)
    if not prefixes:
        return tags
    return [t for t in tags if not any(t.startswith(p) for p in prefixes)]


def _build_proxies_inbounds(
    inbounds_data: dict | list, settings: Settings | None = None
) -> tuple[dict, dict]:
    """Build full multi-protocol Marzban user payload from /api/inbounds."""
    if isinstance(inbounds_data, dict):
        available = [
            proto
            for proto in _SUPPORTED_PROTOCOLS
            if proto in inbounds_data and inbounds_data[proto]
        ]
        if not available:
            available = list(_SUPPORTED_PROTOCOLS)
        proxies = {proto: {} for proto in available}
        inbounds: dict[str, list[str]] = {}
        for proto in available:
            tags = _filter_inbound_tags(
                [
                    ib["tag"]
                    for ib in inbounds_data.get(proto, [])
                    if isinstance(ib, dict) and ib.get("tag")
                ],
                settings,
            )
            if tags:
                inbounds[proto] = tags
        return proxies, inbounds

    proxy_types: set[str] = set()
    inbounds_by_tag: dict[str, dict] = {}
    for ib in inbounds_data:
        if not isinstance(ib, dict):
            continue
        tag = ib.get("tag")
        if tag and tag not in _filter_inbound_tags([tag], settings):
            inbounds_by_tag[tag] = {}
        for proto in ("protocol", "type"):
            p = ib.get(proto)
            if isinstance(p, str):
                proxy_types.add(p.lower())
    proxies = {ptype: {} for ptype in proxy_types if ptype in _SUPPORTED_PROTOCOLS}
    if not proxies:
        proxies = {proto: {} for proto in ("vless", "vmess", "trojan", "shadowsocks")}
    return proxies, inbounds_by_tag


class MarzbanService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token: str | None = None
        self._base = settings.marzban_url.rstrip("/")
        self._warned_http = False
        self._http: httpx.AsyncClient | None = None

    def _warn_if_http_url(self) -> None:
        if self._warned_http or self._settings.marzban_dry_run:
            return
        if self._base.startswith("http://"):
            logger.error(
                "MARZBAN_URL uses http:// but Marzban may require https:// — "
                "trial/provisioning will fail with 'server disconnected'"
            )
            self._warned_http = True

    async def _get_client(self) -> httpx.AsyncClient:
        self._warn_if_http_url()
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base,
                timeout=30.0,
                verify=self._settings.marzban_verify_ssl,
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None
            self._token = None

    async def _ensure_token(self, client: httpx.AsyncClient) -> str:
        if self._token:
            return self._token
        if self._settings.marzban_dry_run:
            self._token = "dry-run-token"
            return self._token
        try:
            resp = await client.post(
                "/api/admin/token",
                data={
                    "username": self._settings.marzban_user,
                    "password": self._settings.marzban_pass,
                },
            )
            resp.raise_for_status()
        except Exception as e:
            raise MarzbanError("token", _format_marzban_error("token", e)) from e
        self._token = resp.json()["access_token"]
        return self._token

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def get_inbounds(self) -> dict | list:
        if self._settings.marzban_dry_run:
            return {
                proto: [{"tag": f"dry-{proto}", "protocol": proto}]
                for proto in _SUPPORTED_PROTOCOLS
            }
        client = await self._get_client()
        token = await self._ensure_token(client)
        resp = await client.get("/api/inbounds", headers=self._headers(token))
        resp.raise_for_status()
        return resp.json()

    async def _default_user_payload(self) -> tuple[dict, dict]:
        now = time.time()
        if now - _INBOUND_CACHE["at"] < _INBOUND_TTL and _INBOUND_CACHE["proxies"]:
            return _INBOUND_CACHE["proxies"], _INBOUND_CACHE["inbounds"]
        try:
            inbounds_data = await self.get_inbounds()
            proxies, inbounds = _build_proxies_inbounds(inbounds_data, self._settings)
        except Exception as e:
            logger.warning("inbounds fetch failed, using defaults: %s", e)
            proxies = {proto: {} for proto in _SUPPORTED_PROTOCOLS}
            inbounds: dict = {}
        _INBOUND_CACHE.update({"at": now, "proxies": proxies, "inbounds": inbounds})
        return proxies, inbounds

    async def health_check(self) -> tuple[bool, str, int]:
        start = time.perf_counter()
        try:
            client = await self._get_client()
            if self._settings.marzban_dry_run:
                ms = int((time.perf_counter() - start) * 1000)
                return True, "DRY_RUN", ms
            await self._ensure_token(client)
            resp = await client.get("/api/system", headers=self._headers(self._token or ""))
            resp.raise_for_status()
            ms = int((time.perf_counter() - start) * 1000)
            return True, "OK", ms
        except MarzbanError as e:
            ms = int((time.perf_counter() - start) * 1000)
            return False, str(e), ms
        except Exception as e:
            ms = int((time.perf_counter() - start) * 1000)
            return False, _format_marzban_error("health_check", e), ms

    def _parse_user(self, data: dict) -> MarzbanUser:
        links = data.get("links")
        return MarzbanUser(
            username=data["username"],
            subscription_url=normalize_subscription_url(data.get("subscription_url")),
            expire=data.get("expire", 0),
            data_limit=data.get("data_limit", 0),
            status=data.get("status", "active"),
            used_traffic=data.get("used_traffic", 0),
            note=data.get("note") or "",
            links=list(links) if links else None,
        )

    def _dry_run_links(self, username: str) -> list[str]:
        host = "127.0.0.1"
        return [
            f"vless://00000000-0000-4000-8000-{username[:12]:0<12}@{host}:2096?type=ws&path=/vless#dry-{username}",
            f"trojan://dry-{username}@{host}:2097?type=ws&path=/trojan#dry-{username}",
            f"vmess://eyJ2IjoiMiIsInBzIjoiZHJ5LXN1YiIsImFkZCI6Intob3N0fSIsInBvcnQiOjIwOTV9".replace(
                "{host}", host
            ),
            f"ss://dry-{username}@{host}:2098#dry-{username}",
        ]

    async def create_user(
        self,
        username: str,
        data_limit: int,
        expire_timestamp: int,
        note: str = "",
    ) -> MarzbanUser:
        if self._settings.marzban_dry_run:
            return MarzbanUser(
                username=username,
                subscription_url=f"https://sub.example.com/sub/dry-{username}",
                expire=expire_timestamp,
                data_limit=data_limit,
                status="active",
                links=self._dry_run_links(username),
            )
        proxies, inbounds = await self._default_user_payload()
        payload: dict[str, Any] = {
            "username": username,
            "data_limit": data_limit,
            "expire": expire_timestamp,
            "status": "active",
            "note": note,
            "proxies": proxies,
            "inbounds": inbounds,
        }
        client = await self._get_client()
        token = await self._ensure_token(client)
        try:
            resp = await client.post("/api/user", json=payload, headers=self._headers(token))
            resp.raise_for_status()
        except Exception as e:
            raise MarzbanError("create_user", _format_marzban_error("create_user", e)) from e
        return self._parse_user(resp.json())

    async def get_user(self, username: str) -> MarzbanUser | None:
        if self._settings.marzban_dry_run:
            return MarzbanUser(
                username=username,
                subscription_url=f"https://sub.example.com/sub/dry-{username}",
                expire=int(time.time()) + 86400 * 30,
                data_limit=0,
                status="active",
                links=self._dry_run_links(username),
            )
        client = await self._get_client()
        token = await self._ensure_token(client)
        try:
            resp = await client.get(f"/api/user/{username}", headers=self._headers(token))
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
        except Exception as e:
            raise MarzbanError("get_user", _format_marzban_error("get_user", e)) from e
        return self._parse_user(resp.json())

    async def list_users(
        self, offset: int = 0, limit: int = 20, search: str | None = None
    ) -> tuple[list[MarzbanUserListItem], int]:
        if self._settings.marzban_dry_run:
            return [], 0
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if search:
            params["search"] = search
        client = await self._get_client()
        token = await self._ensure_token(client)
        resp = await client.get("/api/users", params=params, headers=self._headers(token))
        resp.raise_for_status()
        data = resp.json()
        users = [
            MarzbanUserListItem(
                username=u["username"],
                status=u.get("status", ""),
                used_traffic=u.get("used_traffic", 0),
                data_limit=u.get("data_limit", 0),
                expire=u.get("expire", 0),
                note=u.get("note") or "",
            )
            for u in data.get("users", [])
        ]
        return users, int(data.get("total", len(users)))

    async def modify_user(
        self,
        username: str,
        *,
        expire: int | None = None,
        status: str | None = None,
        data_limit: int | None = None,
    ) -> MarzbanUser:
        if self._settings.marzban_dry_run:
            return MarzbanUser(
                username=username,
                subscription_url=f"https://sub.example.com/sub/dry-{username}",
                expire=expire or int(time.time()) + 86400 * 30,
                data_limit=data_limit or 0,
                status=status or "active",
            )
        payload: dict[str, Any] = {}
        if expire is not None:
            payload["expire"] = expire
        if status is not None:
            payload["status"] = status
        if data_limit is not None:
            payload["data_limit"] = data_limit
        client = await self._get_client()
        token = await self._ensure_token(client)
        try:
            resp = await client.put(
                f"/api/user/{username}", json=payload, headers=self._headers(token)
            )
            resp.raise_for_status()
        except Exception as e:
            raise MarzbanError("modify_user", _format_marzban_error("modify_user", e)) from e
        return self._parse_user(resp.json())

    async def reset_user_traffic(self, username: str) -> None:
        if self._settings.marzban_dry_run:
            return
        client = await self._get_client()
        token = await self._ensure_token(client)
        resp = await client.post(
            f"/api/user/{username}/reset", headers=self._headers(token)
        )
        resp.raise_for_status()

    async def revoke_subscription(self, username: str) -> None:
        if self._settings.marzban_dry_run:
            return
        client = await self._get_client()
        token = await self._ensure_token(client)
        resp = await client.post(
            f"/api/user/{username}/revoke_sub", headers=self._headers(token)
        )
        resp.raise_for_status()

    async def delete_user(self, username: str) -> None:
        if self._settings.marzban_dry_run:
            return
        client = await self._get_client()
        token = await self._ensure_token(client)
        resp = await client.delete(f"/api/user/{username}", headers=self._headers(token))
        if resp.status_code not in (200, 404):
            resp.raise_for_status()

    async def list_nodes(self) -> list[dict]:
        if self._settings.marzban_dry_run:
            return []
        client = await self._get_client()
        token = await self._ensure_token(client)
        resp = await client.get("/api/nodes", headers=self._headers(token))
        resp.raise_for_status()
        return resp.json()
