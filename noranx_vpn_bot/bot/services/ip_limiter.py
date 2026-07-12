"""IP limiter API client for MarzneshinIpLimit."""

import time

import httpx

from bot.config import Settings
from bot.utils.logging import get_logger

logger = get_logger("ip_limiter")


class IpLimiterService:
    def __init__(self, settings: Settings) -> None:
        self._base = settings.ip_limiter_url.rstrip("/")
        self._user = settings.ip_limiter_api_user
        self._password = settings.ip_limiter_api_pass
        self._skip = settings.provision_skip_limiters
        self._token: str | None = None
        self._http: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self._base, timeout=15.0)
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None
            self._token = None

    async def _auth_headers(self, client: httpx.AsyncClient) -> dict[str, str]:
        if not self._user:
            return {}
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        resp = await client.post(
            "/login",
            json={"username": self._user, "password": self._password},
        )
        if resp.status_code == 404:
            return {}
        if resp.is_success:
            data = resp.json()
            self._token = data.get("access_token") or data.get("token", "")
            if self._token:
                return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def health_check(self) -> tuple[bool, str, int]:
        start = time.perf_counter()
        if self._skip:
            ms = int((time.perf_counter() - start) * 1000)
            return True, "SKIPPED", ms
        try:
            client = await self._get_client()
            resp = await client.get("/health", timeout=10.0)
            if resp.status_code == 404:
                headers = await self._auth_headers(client)
                if not headers:
                    ms = int((time.perf_counter() - start) * 1000)
                    return False, "auth failed", ms
                resp = await client.get(
                    "/special_limit",
                    params={"user": "__health__"},
                    headers=headers,
                )
            ms = int((time.perf_counter() - start) * 1000)
            ok = resp.status_code < 500 and (
                resp.status_code == 200 or resp.status_code == 404
            )
            return ok, "OK" if ok else resp.text[:120], ms
        except Exception as e:
            ms = int((time.perf_counter() - start) * 1000)
            return False, str(e), ms

    async def get_limit(self, username: str) -> dict | None:
        if self._skip:
            return None
        client = await self._get_client()
        headers = await self._auth_headers(client)
        if not headers:
            return None
        resp = await client.get(
            "/special_limit",
            params={"user": username},
            headers=headers,
        )
        if resp.status_code >= 400:
            return None
        return resp.json()

    async def set_limit(self, username: str, limit: int) -> None:
        if self._skip:
            logger.warning("Skipping IP limiter for %s", username)
            return
        client = await self._get_client()
        headers = await self._auth_headers(client)
        resp = await client.post(
            "/update_special_limit",
            json={"user": username, "limit": limit},
            headers=headers,
        )
        resp.raise_for_status()

    async def remove_limit(self, username: str) -> None:
        if self._skip:
            return
        try:
            client = await self._get_client()
            headers = await self._auth_headers(client)
            resp = await client.post(
                "/remove_special_limit",
                json={"user": username},
                headers=headers,
            )
            if resp.status_code not in (200, 404):
                resp.raise_for_status()
        except Exception as e:
            logger.warning("IP limiter cleanup failed for %s: %s", username, e)
