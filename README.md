# NoranX VPN Stack

Private monorepo: Telegram bot, webhooks, Marzban integration, IP limiter, nginx/systemd configs, and production deploy artifacts.

## Layout

| Path | Description |
|------|-------------|
| `noranx_vpn_bot/` | Telegram bot, FastAPI webhooks (`:8080`), Alembic, infrastructure nginx/systemd |
| `MarzneshinIpLimit/` | IP limiter API service (Python) |
| `deploy/opt-marzban/` | Marzban docker-compose + `.env` (production `/opt/marzban`) |
| `deploy/opt-scripts/` | Protocol verify + Marzban setup scripts (`/opt/scripts`) |
| `deploy/opt-marzneshiniplimit/` | IP limiter runtime config (`/opt/marzneshiniplimit`) |
| `deploy/root-scripts/` | VPS deploy helpers (`/root/scripts`) |

## Production bot (systemd)

```bash
cd noranx_vpn_bot
docker compose up -d postgres redis
.venv/bin/alembic upgrade head
systemctl enable --now noranx-bot
```

See `noranx_vpn_bot/README.md` for full bot documentation.

## Security note

This repository includes `.env` files with live secrets by operator request. Restrict access to the private repo and rotate credentials if exposed.
