#!/usr/bin/env python3
"""Verify test.ibaxgames.ir multi-protocol CDN setup."""

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
DOMAIN = "test.ibaxgames.ir"
BIGADLER = "test.bigadler.ir"


def ok(msg):
    global PASS
    PASS += 1
    print(f"  PASS  {msg}")


def bad(msg, detail=""):
    global FAIL
    FAIL += 1
    line = f"  FAIL  {msg}"
    if detail:
        line += f"\n        {detail}"
    print(line)


def warn(msg, detail=""):
    global WARN
    WARN += 1
    line = f"  WARN  {msg}"
    if detail:
        line += f"\n        {detail}"
    print(line)


def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def ws_upgrade(url, host=None):
    host = host or DOMAIN
    http1 = "--http1.1" if url.startswith("https") else ""
    cmd = (
        f'curl -si --max-time 8 {http1} -H "Host: {host}" '
        '-H "Connection: Upgrade" -H "Upgrade: websocket" '
        '-H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" '
        f'"{url}"'
    )
    code, out = run(cmd)
    return "101 Switching Protocols" in out, out.splitlines()[0] if out else "no response"


def load_env():
    env = {}
    try:
        with open("/opt/marzban/.env") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k] = v.strip().strip('"')
    except OSError as e:
        bad("read .env", str(e))
    return env


def marzban_api(user):
    env = load_env()
    user_admin = env.get("SUDO_USERNAME", "valtor")
    password = env.get("SUDO_PASSWORD", "")
    port = env.get("UVICORN_PORT", "18000")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    base = f"https://127.0.0.1:{port}"

    data = urllib.parse.urlencode({"username": user_admin, "password": password}).encode()
    req = urllib.request.Request(
        f"{base}/api/admin/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        token = json.load(resp)["access_token"]

    req = urllib.request.Request(
        f"{base}/api/user/{urllib.parse.quote(user)}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        return json.load(resp)


def check_listeners():
    print("\n[1-3] Xray listeners")
    code, out = run("ss -tlnp | grep xray")
    if code != 0:
        bad("xray not listening")
        return
    for port in ("10000", "10002", "10003"):
        if f"127.0.0.1:{port}" in out:
            ok(f"127.0.0.1:{port} listening")
        else:
            bad(f"127.0.0.1:{port} missing")
    for port in ("2095", "2097", "2096", "2098"):
        if f":{port}" in out and "127.0.0.1" not in out.split(f":{port}")[0][-20:]:
            bad(f"public port {port} still bound", out)
        else:
            ok(f"port {port} not publicly bound")


def check_nginx():
    print("\n[4] nginx syntax")
    code, out = run("nginx -t")
    if code == 0:
        ok("nginx -t")
    else:
        bad("nginx -t", out.strip())


def check_origin_ws():
    print("\n[5-7] Origin WebSocket upgrades")
    for path in ("/ws", "/trojan", "/vmess"):
        passed, first = ws_upgrade(f"http://127.0.0.1{path}")
        if passed:
            ok(f"origin {path} -> 101")
        else:
            bad(f"origin {path}", first)


def check_tls():
    print("\n[8] TLS certificate")
    code, out = run(
        f'echo | openssl s_client -connect 127.0.0.1:443 -servername {DOMAIN} 2>/dev/null | openssl x509 -noout -subject 2>/dev/null'
    )
    if code == 0 and DOMAIN in out:
        ok(f"TLS cert for {DOMAIN}")
    else:
        bad("TLS cert check", out.strip() or "failed")


def check_cdn_ws():
    print("\n[9-11] CDN WebSocket upgrades")
    for path in ("/ws", "/trojan", "/vmess"):
        passed, first = ws_upgrade(f"https://{DOMAIN}{path}")
        if passed:
            ok(f"CDN {path} -> 101")
        else:
            warn(f"CDN {path}", first)


def check_api_links(user):
    print("\n[12-14] Marzban subscription links")
    try:
        data = marzban_api(user)
    except Exception as e:
        bad("Marzban API", str(e))
        return

    links = data.get("links") or []
    ibax_count = len([l for l in links if DOMAIN in l or l.startswith("vmess://")])

    if ibax_count == 6:
        ok(f"ibax profile count = 6")
    else:
        bad(f"ibax profile count = {ibax_count} (expected 6)")

    sub_url = data.get("subscription_url", "")
    if sub_url:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        raw = None
        last_err = None
        for _ in range(3):
            try:
                with urllib.request.urlopen(sub_url, context=ctx, timeout=20) as resp:
                    raw = resp.read()
                if raw and not raw.lstrip().startswith(b"<"):
                    break
            except Exception as e:
                last_err = e
                import time
                time.sleep(2)
        if raw is None:
            bad("subscription fetch/decode", str(last_err))
            return
        try:
            text = base64.b64decode(raw).decode("utf-8", errors="replace")
        except Exception:
            text = raw.decode("utf-8", errors="replace")

        if any(line.startswith("ss://") for line in text.splitlines()):
            bad("forbidden protos in sub", "ss:// line found")
        elif "reality" in text.lower() and "pbk=" in text.lower():
            bad("forbidden protos in sub", "reality params found")
        elif f"{DOMAIN}" in text and "/xh" in text and "xhttp" in text.lower():
            bad("ibax xHTTP still in sub")
        else:
            ok("no SS/REALITY/ibax-xHTTP in sub")

        if BIGADLER in text and ("%2Fws" in text or "/ws" in text):
            ok("bigadler VLESS WS still in sub")
        else:
            bad("bigadler VLESS WS missing from sub")
    else:
        bad("no subscription_url")


def check_html_sub(user):
    print("\n[15] HTML subscription page")
    try:
        data = marzban_api(user)
        sub_url = data.get("subscription_url", "")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(sub_url, headers={"Accept": "text/html"})
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        count = len(re.findall(re.escape(DOMAIN), html))
        boxes = html.count('class="uri-box"')
        if boxes >= 6:
            ok(f"HTML page has {boxes} uri-box entries")
        else:
            bad(f"HTML uri-box count = {boxes} (expected >= 6)")
        if "Trojan" in html or "trojan" in html:
            ok("HTML mentions Trojan")
        else:
            warn("HTML may not mention Trojan in visible text")
    except Exception as e:
        bad("HTML sub page", str(e))


def main():
    parser = argparse.ArgumentParser(description="Verify ibax multi-protocol CDN")
    parser.add_argument("--user", default="valtor", help="Marzban username to test")
    args = parser.parse_args()

    print(f"=== verify-ibax-protocols.py (user={args.user}) ===")
    check_listeners()
    check_nginx()
    check_origin_ws()
    check_tls()
    check_cdn_ws()
    check_api_links(args.user)
    check_html_sub(args.user)

    print(f"\n=== SUMMARY: {PASS} pass, {FAIL} fail, {WARN} warn ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
