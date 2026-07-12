# MarzneshinIpLimit deployment

Bot API client: [`bot/services/ip_limiter.py`](../../bot/services/ip_limiter.py)

1. Clone https://github.com/muttehit/MarzneshinIpLimit
2. Configure `/opt/marzneshiniplimit/config.json`:

```json
{
  "GENERAL_LIMIT": 1,
  "PANEL_USERNAME": "valtor",
  "PANEL_PASSWORD": "your-marzban-password",
  "PANEL_DOMAIN": "127.0.0.1:8000",
  "SECRET_KEY": "change-me",
  "API_USERNAME": "api",
  "API_PASSWORD": "api-secret",
  "CHECK_INTERVAL": 30,
  "TIME_TO_ACTIVE_USERS": 2400,
  "IP_LOCATION": "IR",
  "outOfLimitNumber": 2
}
```

`PANEL_DOMAIN` must reach Marzban API (HTTPS on `127.0.0.1:8000` when SSL enabled).

3. Build and run (GHCR image may be private — build locally):

```bash
cd /root/MarzneshinIpLimit && docker build -t marzneshiniplimit:local .
docker run -d --name marzneshiniplimit --restart always --network host \
  -e PORT=6284 \
  -v /opt/marzneshiniplimit/config.json:/marzneshiniplimitcode/config.json \
  marzneshiniplimit:local
```

4. In bot `.env`:

```env
IP_LIMITER_URL=http://127.0.0.1:6284
IP_LIMITER_API_USER=api
IP_LIMITER_API_PASS=api-secret
PROVISION_SKIP_LIMITERS=false
```

Bot calls: `POST /login` then `POST /update_special_limit` with `{"user": "username", "limit": N}`.
