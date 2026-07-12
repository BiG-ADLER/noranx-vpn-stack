# NoranX VPN Bot

Telegram sales bot for Marzban VPN with wallet, NowPayments, dual limiters (device + IP), and Persian UI.

## Production deployment (systemd)

On the VPS, run the bot via **systemd only** — do not use `docker compose up bot` or `./scripts/start.sh` alongside the service.

```bash
docker compose up -d postgres redis
.venv/bin/alembic upgrade head
systemctl enable --now noranx-bot
systemctl status noranx-bot
```

`start.sh` is for local/dev use when systemd is not active.

## Quick start

```bash
cp .env.example .env
# Edit BOT_TOKEN, ADMIN_IDS, MARZBAN_*, limiter URLs, NOWPAYMENTS_*

docker compose up -d postgres redis
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_plans.py
./scripts/start.sh
```

Or one-liner after `.env` is configured:

```bash
./scripts/start.sh
```

## HTTPS / webhooks (bot.bigadler.xyz)

Nginx config: `infrastructure/nginx/bot.bigadler.xyz.conf`

- Health: `https://bot.bigadler.xyz/health`
- NowPayments IPN: `https://bot.bigadler.xyz/webhooks/nowpayments`
- Marzban (localhost only): `http://127.0.0.1:8080/webhooks/marzban`

## With Docker (dev only — do not use bot service in production)

The `bot` service in docker-compose is for development. Production uses `noranx-bot.service` on the host.

```bash
# Use 127.0.0.1 for postgres/redis when bot uses network_mode: host
DATABASE_URL=postgresql+asyncpg://noranx:noranx@127.0.0.1:5433/noranx_bot
REDIS_URL=redis://127.0.0.1:6380/0
docker compose up -d --build
docker compose exec bot alembic upgrade head
docker compose exec bot python scripts/seed_plans.py
```

## Infrastructure

See [infrastructure/README.md](infrastructure/README.md) for device limiter, IP limiter, and nginx setup.

## Health check

```bash
MARZBAN_DRY_RUN=true PROVISION_SKIP_LIMITERS=true python scripts/health_check.py
```

## Admin commands

- `/admin` — admin panel
- `/debug` — system health
- `/sync_user <username>` — reconcile subscription
- `/re_enable <username>` — re-enable after IP block
- `/wallet_add <tg_id> <toman>`
- `/discount_new <percent> [max_uses]`
- `/package_add <toman>`
- `/order_logs <order_id>`

## Mock C2C (testing)

1. User selects recharge package → gets `external_id`
2. `POST /webhooks/c2c/mock/{external_id}` with header `x-c2c-secret: <C2C_WEBHOOK_SECRET>`
