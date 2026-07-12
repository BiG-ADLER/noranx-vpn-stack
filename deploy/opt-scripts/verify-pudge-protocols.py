#!/usr/bin/env python3
"""Verify pudge.ibaxgames.ir (DE node) multi-protocol CDN setup."""

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
DOMAIN = "pudge.ibaxgames.ir"
DE_IP = "178.83.46.103"


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


def ws_upgrade(url, host=None, insecure=False):
    host = host or DOMAIN
    http1 = "--http1.1" if url.startswith("https") else ""
    kinsecure = "-k" if insecure or (url.startswith("https://") and DE_IP in url) else ""
    cmd = (
        f'curl -si --max-time 12 {http1} {kinsecure} -H "Host: {host}" '
        '-H "Connection: Upgrade" -H "Upgrade: websocket" '
        '-H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" '
        f'"{url}"'
    )
    code, out = run(cmd)
    return "101 Switching Protocols" in out, out.splitlines()[0] if out else "no response"


def load_env():
    env = {}
    with open("/opt/marzban/.env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v.strip().strip('"')
    return env


def marzban_api(user):
    env = load_env()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    base = f"https://127.0.0.1:{env.get('UVICORN_PORT', '18000')}"
    data = urllib.parse.urlencode(
        {"username": env["SUDO_USERNAME"], "password": env["SUDO_PASSWORD"]}
    ).encode()
    req = urllib.request.Request(
        f"{base}/api/admin/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    token = json.load(urllib.request.urlopen(req, context=ctx, timeout=20))["access_token"]
    req = urllib.request.Request(
        f"{base}/api/user/{urllib.parse.quote(user)}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return json.load(urllib.request.urlopen(req, context=ctx, timeout=20))


def count_domain_in_links(links, domain):
    count = 0
    for line in links:
        if domain in line:
            count += 1
        elif line.startswith("vmess://"):
            try:
                j = json.loads(base64.urlsafe_b64decode(line.split("://", 1)[1] + "=="))
                if j.get("add") == domain:
                    count += 1
            except Exception:
                pass
    return count


def check_node():
    print("\n[1] Marzban DE node")
    env = load_env()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    base = f"https://127.0.0.1:{env.get('UVICORN_PORT', '18000')}"
    data = urllib.parse.urlencode(
        {"username": env["SUDO_USERNAME"], "password": env["SUDO_PASSWORD"]}
    ).encode()
    req = urllib.request.Request(
        f"{base}/api/admin/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    token = json.load(urllib.request.urlopen(req, context=ctx, timeout=20))["access_token"]
    req = urllib.request.Request(f"{base}/api/nodes", headers={"Authorization": f"Bearer {token}"})
    nodes = json.load(urllib.request.urlopen(req, context=ctx, timeout=20))
    de = [n for n in nodes if n.get("address") == DE_IP or n.get("name") == "DE"]
    if not de:
        bad("DE node not found in panel")
        return
    node = de[0]
    if node.get("status") == "connected":
        ok(f"node {node.get('name')} ({node.get('address')}) connected")
    else:
        bad(f"node status = {node.get('status')}", str(node.get("message")))


def check_hosts_api():
    print("\n[2] Marzban pudge hosts")
    env = load_env()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    base = f"https://127.0.0.1:{env.get('UVICORN_PORT', '18000')}"
    data = urllib.parse.urlencode(
        {"username": env["SUDO_USERNAME"], "password": env["SUDO_PASSWORD"]}
    ).encode()
    req = urllib.request.Request(
        f"{base}/api/admin/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    token = json.load(urllib.request.urlopen(req, context=ctx, timeout=20))["access_token"]
    req = urllib.request.Request(f"{base}/api/hosts", headers={"Authorization": f"Bearer {token}"})
    hosts_raw = json.load(urllib.request.urlopen(req, context=ctx, timeout=20))
    pudge = []
    tags_with_pudge = []
    for tag, entries in hosts_raw.items():
        if not isinstance(entries, list):
            continue
        tag_hosts = [h for h in entries if h.get("address") == DOMAIN and not h.get("is_disabled")]
        if tag_hosts:
            tags_with_pudge.append(tag)
            pudge.extend(tag_hosts)
    if len(pudge) == 6:
        ok(f"pudge host count = 6")
    else:
        bad(f"pudge host count = {len(pudge)} (expected 6)")
    for tag in ("VLESS WS", "Trojan WS", "VMESS WS"):
        if tag in tags_with_pudge:
            ok(f"host inbound {tag}")
        else:
            bad(f"missing host inbound {tag}")


def check_cdn_ws():
    print("\n[3-5] CDN WebSocket upgrades (Cloudflare)")
    for path in ("/ws", "/trojan", "/vmess"):
        passed, first = ws_upgrade(f"https://{DOMAIN}{path}")
        if passed:
            ok(f"CDN {path} -> 101")
        else:
            bad(f"CDN {path}", first)


def check_direct_de():
    print("\n[6-8] Direct DE origin WebSocket")
    for path in ("/ws", "/trojan", "/vmess"):
        passed, first = ws_upgrade(f"https://{DE_IP}{path}", host=DOMAIN)
        if passed:
            ok(f"DE origin {path} -> 101")
        else:
            bad(f"DE origin {path}", first)


def check_api_links(user):
    print("\n[9] User subscription links")
    try:
        data = marzban_api(user)
    except Exception as e:
        bad("Marzban API", str(e))
        return

    links = data.get("links") or []
    pudge_count = count_domain_in_links(links, DOMAIN)
    if pudge_count == 6:
        ok(f"pudge profile count = 6")
    else:
        bad(f"pudge profile count = {pudge_count} (expected 6)")

    sub_url = data.get("subscription_url", "")
    if not sub_url:
        bad("no subscription_url")
        return

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(sub_url, context=ctx, timeout=20) as resp:
        raw = resp.read()
    text = base64.b64decode(raw).decode("utf-8", errors="replace")
    sub_lines = [line for line in text.splitlines() if line.strip()]
    sub_pudge = count_domain_in_links(sub_lines, DOMAIN)
    if sub_pudge >= 6:
        ok(f"base64 sub has {sub_pudge} pudge entries")
    else:
        bad(f"base64 sub pudge count = {sub_pudge} (expected >= 6)")


def check_html_sub(user):
    print("\n[10] HTML subscription page")
    try:
        data = marzban_api(user)
        sub_url = data.get("subscription_url", "")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(sub_url, headers={"Accept": "text/html"})
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        pudge = html.count(DOMAIN)
        boxes = html.count('class="uri-box"')
        if pudge >= 6:
            ok(f"HTML mentions {DOMAIN} x{pudge}")
        else:
            bad(f"HTML pudge count = {pudge} (expected >= 6)")
        if boxes >= 13:
            ok(f"HTML page has {boxes} uri-box entries (ibax+pudge+bigadler)")
        elif boxes >= 6:
            warn(f"HTML uri-box count = {boxes} (expected >= 13 with all regions)")
        else:
            bad(f"HTML uri-box count = {boxes}")
    except Exception as e:
        bad("HTML sub page", str(e))


def main():
    parser = argparse.ArgumentParser(description="Verify pudge DE node CDN")
    parser.add_argument("--user", default="valtor", help="Marzban username to test")
    args = parser.parse_args()

    print(f"=== verify-pudge-protocols.py (user={args.user}) ===")
    check_node()
    check_hosts_api()
    check_cdn_ws()
    check_direct_de()
    check_api_links(args.user)
    check_html_sub(args.user)

    print(f"\n=== SUMMARY: {PASS} pass, {FAIL} fail, {WARN} warn ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
