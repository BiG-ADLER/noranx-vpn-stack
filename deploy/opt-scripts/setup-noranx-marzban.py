#!/usr/bin/env python3
"""Add isolated NRX inbounds, noranx.ir hosts, and probe user to Marzban."""

from __future__ import annotations

import copy
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROBE_USER = "noranx_cdn_probe"
NRX_INBOUNDS = [
    {
        "tag": "NRX-VLESS-WS",
        "listen": "127.0.0.1",
        "port": 10010,
        "protocol": "vless",
        "path": "/ws",
        "network": "ws",
    },
    {
        "tag": "NRX-TROJAN-WS",
        "listen": "127.0.0.1",
        "port": 10012,
        "protocol": "trojan",
        "path": "/trojan",
        "network": "ws",
    },
    {
        "tag": "NRX-VMESS-WS",
        "listen": "127.0.0.1",
        "port": 10013,
        "protocol": "vmess",
        "path": "/vmess",
        "network": "ws",
    },
]

HOST_SPECS = [
    ("test.noranx.ir", "NRX-VLESS-WS", "/ws", "PL noranx VLESS"),
    ("test.noranx.ir", "NRX-TROJAN-WS", "/trojan", "PL noranx Trojan"),
    ("test.noranx.ir", "NRX-VMESS-WS", "/vmess", "PL noranx VMESS"),
    ("pudge.noranx.ir", "NRX-VLESS-WS", "/ws", "DE noranx VLESS"),
    ("pudge.noranx.ir", "NRX-TROJAN-WS", "/trojan", "DE noranx Trojan"),
    ("pudge.noranx.ir", "NRX-VMESS-WS", "/vmess", "DE noranx VMESS"),
]


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    with open("/opt/marzban/.env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v.strip().strip('"')
    return env


def api_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class MarzbanAdmin:
    def __init__(self) -> None:
        env = load_env()
        self.base = f"https://127.0.0.1:{env.get('UVICORN_PORT', '18000')}"
        self.ctx = api_ctx()
        data = urllib.parse.urlencode(
            {"username": env["SUDO_USERNAME"], "password": env["SUDO_PASSWORD"]}
        ).encode()
        req = urllib.request.Request(
            f"{self.base}/api/admin/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, context=self.ctx, timeout=20) as resp:
            self.token = json.load(resp)["access_token"]

    def _req(self, method: str, path: str, body: dict | None = None) -> dict | list:
        headers = {"Authorization": f"Bearer {self.token}"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.base}{path}", data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(req, context=self.ctx, timeout=120) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}

    def get_core(self) -> dict:
        return self._req("GET", "/api/core/config")

    def put_core(self, cfg: dict) -> None:
        self._req("PUT", "/api/core/config", cfg)

    def get_hosts(self) -> dict:
        return self._req("GET", "/api/hosts")

    def put_hosts(self, hosts: dict) -> None:
        self._req("PUT", "/api/hosts", hosts)

    def get_user(self, username: str) -> dict | None:
        try:
            return self._req("GET", f"/api/user/{urllib.parse.quote(username)}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def create_user(self, payload: dict) -> dict:
        return self._req("POST", "/api/user", payload)

    def modify_user(self, username: str, payload: dict) -> dict:
        return self._req("PUT", f"/api/user/{urllib.parse.quote(username)}", payload)


def template_inbound(spec: dict, core: dict) -> dict:
    proto = spec["protocol"]
    tag_map = {"vless": "VLESS WS", "trojan": "Trojan WS", "vmess": "VMESS WS"}
    for ib in core.get("inbounds", []):
        if ib.get("tag") == tag_map[proto]:
            base = copy.deepcopy(ib)
            base["tag"] = spec["tag"]
            base["listen"] = spec["listen"]
            base["port"] = spec["port"]
            base["settings"]["clients"] = []
            if proto == "vless":
                base["streamSettings"]["wsSettings"]["path"] = spec["path"]
            elif proto == "trojan":
                base["streamSettings"]["wsSettings"]["path"] = spec["path"]
            else:
                base["streamSettings"]["wsSettings"]["path"] = spec["path"]
            return base
    raise RuntimeError(f"no template inbound for {proto}")


def host_row(domain: str, path: str, remark: str, *, tls: bool) -> dict:
    return {
        "remark": f"{remark} {'443' if tls else '80'} - {{USERNAME}}",
        "address": domain,
        "port": 443 if tls else 80,
        "sni": domain if tls else "",
        "host": domain,
        "path": path,
        "security": "tls" if tls else "none",
        "alpn": "",
        "fingerprint": "",
        "allowinsecure": None,
        "is_disabled": False,
        "mux_enable": False,
        "fragment_setting": None,
        "noise_setting": None,
        "random_user_agent": False,
        "use_sni_as_host": False,
    }


def build_nrx_hosts() -> dict[str, list[dict]]:
    hosts: dict[str, list[dict]] = {
        "NRX-VLESS-WS": [],
        "NRX-TROJAN-WS": [],
        "NRX-VMESS-WS": [],
    }
    for domain, tag, path, remark in HOST_SPECS:
        hosts[tag].append(host_row(domain, path, remark, tls=False))
        hosts[tag].append(host_row(domain, path, remark, tls=True))
    return hosts


def main() -> int:
    api = MarzbanAdmin()
    core = api.get_core()
    existing_tags = {ib["tag"] for ib in core.get("inbounds", [])}

    added = []
    for spec in NRX_INBOUNDS:
        if spec["tag"] not in existing_tags:
            core["inbounds"].append(template_inbound(spec, core))
            added.append(spec["tag"])
    if added:
        print("Adding inbounds:", ", ".join(added))
        api.put_core(core)
        time.sleep(3)

    hosts = api.get_hosts()
    nrx_hosts = build_nrx_hosts()
    for tag, rows in nrx_hosts.items():
        hosts.setdefault(tag, [])
        existing_addrs = {(h.get("address"), h.get("port"), h.get("path")) for h in hosts[tag]}
        for row in rows:
            key = (row["address"], row["port"], row["path"])
            if key not in existing_addrs:
                hosts[tag].append(row)
    api.put_hosts(hosts)
    print("Hosts updated for NRX tags")

    expire = int(time.time()) + 30 * 86400
    nrx_inbounds = {
        "vless": ["NRX-VLESS-WS"],
        "trojan": ["NRX-TROJAN-WS"],
        "vmess": ["NRX-VMESS-WS"],
    }
    payload = {
        "username": PROBE_USER,
        "proxies": {"vless": {}, "trojan": {}, "vmess": {}},
        "inbounds": nrx_inbounds,
        "data_limit": 500 * 1024 * 1024,
        "expire": expire,
        "status": "active",
        "note": "noranx CDN probe — manual links only",
    }
    user = api.get_user(PROBE_USER)
    if user:
        api.modify_user(
            PROBE_USER,
            {
                "proxies": payload["proxies"],
                "inbounds": payload["inbounds"],
                "data_limit": payload["data_limit"],
                "expire": payload["expire"],
                "status": "active",
            },
        )
        print(f"Updated probe user {PROBE_USER}")
    else:
        api.create_user(payload)
        print(f"Created probe user {PROBE_USER}")

    user = api.get_user(PROBE_USER)
    links = [l for l in (user or {}).get("links", []) if _link_has_noranx(l)]
    out = Path("/root/logs/noranx-probe-links.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(links) + ("\n" if links else ""))
    print(f"Probe noranx links: {len(links)} (saved to {out})")

    _strip_nrx_from_production_users(api)
    return 0 if len(links) == 12 else 1


def _link_has_noranx(link: str) -> bool:
    if "noranx.ir" in link:
        return True
    if link.startswith("vmess://"):
        import base64

        payload = link.split("vmess://", 1)[1]
        pad = "=" * ((4 - len(payload) % 4) % 4)
        try:
            data = json.loads(base64.urlsafe_b64decode(payload + pad))
            return "noranx.ir" in (data.get("add") or "")
        except Exception:
            return False
    return False


def _strip_nrx_from_production_users(api: MarzbanAdmin) -> None:
    """Marzban may auto-attach new inbounds to existing users — remove NRX- from all except probe."""
    offset = 0
    fixed = 0
    while True:
        batch = api._req("GET", f"/api/users?offset={offset}&limit=100")
        users = batch.get("users", [])
        if not users:
            break
        for row in users:
            uname = row["username"]
            if uname == PROBE_USER:
                continue
            full = api.get_user(uname)
            if not full:
                continue
            inb = full.get("inbounds") or {}
            new_inb: dict[str, list[str]] = {}
            changed = False
            for proto, tags in inb.items():
                filtered = [t for t in tags if not t.startswith("NRX-")]
                if filtered != tags:
                    changed = True
                if filtered:
                    new_inb[proto] = filtered
            if not changed:
                continue
            status = full.get("status", "active")
            if status not in ("active", "disabled", "on_hold"):
                status = "disabled"
            api.modify_user(
                uname,
                {
                    "proxies": full.get("proxies", {}),
                    "inbounds": new_inb,
                    "status": status,
                    "data_limit": full.get("data_limit", 0),
                    "expire": full.get("expire"),
                    "note": full.get("note") or "",
                },
            )
            fixed += 1
        offset += len(users)
        if len(users) < 100:
            break
    if fixed:
        print(f"Stripped NRX inbounds from {fixed} production user(s)")


if __name__ == "__main__":
    sys.exit(main())
