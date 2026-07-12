#!/usr/bin/env python3
"""Verify test.noranx.ir + pudge.noranx.ir CDN rollout and production regression."""

from __future__ import annotations

import argparse
import base64
import json
import re
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request

PASS = FAIL = WARN = 0
PL_DOMAIN = "test.noranx.ir"
DE_DOMAIN = "pudge.noranx.ir"
PROBE_USER = "noranx_cdn_probe"
CUSTOMER_USER = "test_account_noranx"
DE_SSH = "ssh -i /root/.ssh/id_ed25519 -o BatchMode=yes -o ConnectTimeout=20 root@178.83.46.103"


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {msg}")


def bad(msg: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    line = f"  FAIL  {msg}"
    if detail:
        line += f"\n        {detail}"
    print(line)


def warn(msg: str, detail: str = "") -> None:
    global WARN
    WARN += 1
    line = f"  WARN  {msg}"
    if detail:
        line += f"\n        {detail}"
    print(line)


def run(cmd: str, timeout: int = 40) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def ws_upgrade(url: str, host: str | None = None) -> tuple[bool, str]:
    host = host or PL_DOMAIN
    http1 = "--http1.1" if url.startswith("https") else ""
    cmd = (
        f'curl -si --max-time 10 {http1} -H "Host: {host}" '
        '-H "Connection: Upgrade" -H "Upgrade: websocket" '
        '-H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" '
        f'"{url}"'
    )
    code, out = run(cmd)
    first = out.splitlines()[0] if out else "no response"
    return "101 Switching Protocols" in out, first


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    with open("/opt/marzban/.env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v.strip().strip('"')
    return env


def marzban_token() -> str:
    env = load_env()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    port = env.get("UVICORN_PORT", "18000")
    data = urllib.parse.urlencode(
        {"username": env["SUDO_USERNAME"], "password": env["SUDO_PASSWORD"]}
    ).encode()
    req = urllib.request.Request(
        f"https://127.0.0.1:{port}/api/admin/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        return json.load(resp)["access_token"]


def marzban_user(username: str) -> dict:
    token = marzban_token()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    port = load_env().get("UVICORN_PORT", "18000")
    req = urllib.request.Request(
        f"https://127.0.0.1:{port}/api/user/{urllib.parse.quote(username)}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return json.load(resp)


def link_has_noranx(link: str) -> bool:
    if "noranx.ir" in link:
        return True
    if link.startswith("vmess://"):
        payload = link.split("vmess://", 1)[1]
        pad = "=" * ((4 - len(payload) % 4) % 4)
        try:
            data = json.loads(base64.urlsafe_b64decode(payload + pad))
            return "noranx.ir" in (data.get("add") or "")
        except Exception:
            return False
    return False


def count_noranx_links(user: str) -> int:
    data = marzban_user(user)
    return sum(1 for l in data.get("links", []) if link_has_noranx(l))


def check_pl_listeners() -> None:
    print("\n[1] PL NRX xray listeners")
    code, out = run("ss -tlnp | grep xray")
    if code != 0:
        bad("xray not listening on PL")
        return
    for port in ("10010", "10012", "10013"):
        if f"127.0.0.1:{port}" in out:
            ok(f"PL 127.0.0.1:{port}")
        else:
            bad(f"PL 127.0.0.1:{port} missing")


def check_de_listeners() -> None:
    print("\n[2] DE NRX xray listeners (via SSH)")
    code, out = run(f'{DE_SSH} "ss -tlnp | grep -E \'10010|10012|10013\'"')
    if code != 0:
        bad("DE SSH or listeners", out.strip()[:200])
        return
    for port in ("10010", "10012", "10013"):
        if f"127.0.0.1:{port}" in out:
            ok(f"DE 127.0.0.1:{port}")
        else:
            bad(f"DE 127.0.0.1:{port} missing")


def check_nginx() -> None:
    print("\n[3] nginx -t PL + DE")
    code, out = run("nginx -t")
    if code == 0:
        ok("PL nginx -t")
    else:
        bad("PL nginx -t", out.strip())
    code, out = run(f'{DE_SSH} "nginx -t"')
    if code == 0:
        ok("DE nginx -t")
    else:
        bad("DE nginx -t", out.strip())


def check_origin_ws() -> None:
    print("\n[4-5] Origin WebSocket 101")
    for domain in (PL_DOMAIN, DE_DOMAIN):
        host_flag = f'-H "Host: {domain}"' if domain == PL_DOMAIN else ""
        target = "http://127.0.0.1" if domain == PL_DOMAIN else DE_SSH + f' "curl -si --max-time 8 -H \\"Host: {domain}\\" '
        for path in ("/ws", "/trojan", "/vmess"):
            if domain == PL_DOMAIN:
                passed, first = ws_upgrade(f"http://127.0.0.1{path}", host=domain)
            else:
                cmd = (
                    f'{DE_SSH} "curl -si --max-time 8 -H \\"Host: {domain}\\" '
                    '-H \\"Connection: Upgrade\\" -H \\"Upgrade: websocket\\" '
                    '-H \\"Sec-WebSocket-Version: 13\\" -H \\"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\\" '
                    f'http://127.0.0.1{path}"'
                )
                code, out = run(cmd)
                passed = "101 Switching Protocols" in out
                first = out.splitlines()[0] if out else "no response"
            label = f"{domain} origin {path}"
            if passed:
                ok(f"{label} -> 101")
            else:
                bad(label, first)


def check_cdn_ws() -> None:
    print("\n[6] CDN WebSocket 101 (HTTP/1.1)")
    for domain in (PL_DOMAIN, DE_DOMAIN):
        for path in ("/ws", "/trojan", "/vmess"):
            passed, first = ws_upgrade(f"https://{domain}{path}")
            if passed:
                ok(f"CDN {domain}{path} -> 101")
            else:
                warn(f"CDN {domain}{path}", first)


def check_tls() -> None:
    print("\n[7] TLS certificates")
    for domain in (PL_DOMAIN, DE_DOMAIN):
        if domain == PL_DOMAIN:
            cmd = f'echo | openssl s_client -connect 127.0.0.1:443 -servername {domain} 2>/dev/null | openssl x509 -noout -subject 2>/dev/null'
        else:
            cmd = f'{DE_SSH} "echo | openssl s_client -connect 127.0.0.1:443 -servername {domain} 2>/dev/null | openssl x509 -noout -subject 2>/dev/null"'
        code, out = run(cmd)
        if code == 0 and domain in out:
            ok(f"TLS cert {domain}")
        else:
            bad(f"TLS cert {domain}", out.strip())


def check_marzban_nrx() -> None:
    print("\n[8-9] Marzban NRX inbounds + probe user")
    token = marzban_token()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    port = load_env().get("UVICORN_PORT", "18000")
    req = urllib.request.Request(
        f"https://127.0.0.1:{port}/api/inbounds",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        inbounds = json.load(resp)
    tags = []
    for proto_list in inbounds.values():
        tags.extend(ib.get("tag", "") for ib in proto_list if isinstance(ib, dict))
    nrx = [t for t in tags if t.startswith("NRX-")]
    if len(nrx) >= 3:
        ok(f"NRX inbound tags present ({len(nrx)})")
    else:
        bad(f"NRX inbound tags missing ({nrx})")

    probe_count = count_noranx_links(PROBE_USER)
    if probe_count == 12:
        ok(f"{PROBE_USER} has 12 noranx.ir links")
    else:
        bad(f"{PROBE_USER} noranx links = {probe_count} (expected 12)")

    customer_count = count_noranx_links(CUSTOMER_USER)
    if customer_count == 0:
        ok(f"{CUSTOMER_USER} has 0 noranx.ir links (isolated)")
    else:
        bad(f"{CUSTOMER_USER} has {customer_count} noranx.ir links")


def check_regression() -> None:
    print("\n[10-11] Production regression scripts")
    code, out = run("python3 /opt/scripts/verify-ibax-protocols.py --user valtor")
    if code == 0:
        ok("verify-ibax-protocols.py")
    else:
        warn("verify-ibax-protocols.py had failures", out.split("SUMMARY")[-1].strip())
    code, out = run(f'{DE_SSH} "python3 /opt/scripts/verify-pudge-protocols.py"')
    if code == 0:
        ok("verify-pudge-protocols.py on DE")
    else:
        warn("verify-pudge-protocols.py", out.split("SUMMARY")[-1].strip() if "SUMMARY" in out else out[:120])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-regression", action="store_true")
    args = parser.parse_args()

    print("=== verify-noranx-protocols.py ===")
    check_pl_listeners()
    check_de_listeners()
    check_nginx()
    check_origin_ws()
    check_cdn_ws()
    check_tls()
    check_marzban_nrx()
    if not args.skip_regression:
        check_regression()

    print(f"\n=== SUMMARY: {PASS} pass, {FAIL} fail, {WARN} warn ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
