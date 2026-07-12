# Infrastructure Setup (Phase 0)

Run these steps on the same VPS as Marzban before starting the bot.

## 0.1 Marzban `.env` additions

```env
XRAY_SUBSCRIPTION_URL_PREFIX=https://de.bigadler.xyz
WEBHOOK_ADDRESS=http://127.0.0.1:8080/webhooks/marzban
WEBHOOK_SECRET=your-long-random-secret
```

Bot `.env` on the same VPS:

```env
MARZBAN_URL=https://127.0.0.1:8000
MARZBAN_VERIFY_SSL=false
```

Nginx for panel on 443: `nginx/de.bigadler.xyz.conf`. Cloudflare SSL mode: **Full (strict)** with Let's Encrypt on origin.

Add to `/etc/hosts` on the VPS if services call `https://de.bigadler.xyz` locally:

```
127.0.0.1 de.bigadler.xyz
```

Restart: `marzban restart`

## 0.2 Subscription routing (device limiter retired)

`sub.ibaxgames.ir` proxies `/sub/` **directly to Marzban** (`https://127.0.0.1:18000`). See `nginx/sub.ibaxgames.ir.conf`.

The legacy device limiter under `infrastructure/device-limiter/` is **archived** (not started in production). Source and Docker volume are kept for reference only.

## 0.3 MarzneshinIpLimit (IP limiter)

Follow `ip-limiter/README.md`. API must listen on `127.0.0.1:6284` only.

Verify:
```bash
curl -s http://127.0.0.1:6284/health || echo "configure health endpoint per deployment"
```

## 0.4 Bot webhooks nginx

Add `nginx/webhook-location.conf` to proxy public HTTPS to bot port 8080.

## 0.5 Node logs

Confirm MarzneshinIpLimit receives xray access logs from every marzban-node. Missing node logs = IP limits bypassed on that node.

Check worker is running (not just `api.py`):

```bash
docker exec marzneshiniplimit ps aux | grep marzneshiniplimit.py
docker exec marzneshiniplimit grep "Establishing connection" /marzneshiniplimitcode/app.log | tail -3
```

Marzban panel API for this deployment uses `PANEL_DOMAIN=127.0.0.1:18000` (HTTPS). Node log websocket path is `/api/node/{id}/logs` (not the older `/api/nodes/{id}/xray/logs`).

## 0.6 IP limiter and plan device counts

Plan `device_count` in the bot is **cosmetic** (shown in Telegram messages). Enforcement is via **IP limiter** only: concurrent unique public IPs from xray logs.

| Client type | Notes |
|-------------|-------|
| **All clients** | Subscription URL refresh via `sub.ibaxgames.ir` → Marzban (no HWID gate) |
| **Manual import** | Works without subscription refresh limits |

IP limiter blocks multi-location account sharing (requires **different public IPs**, not two devices on the same Wi‑Fi).

Regression check after any limiter/nginx change:

```bash
./scripts/limiter_audit.sh
```
