#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if systemctl is-active --quiet noranx-bot 2>/dev/null; then
  echo "noranx-bot.service is already running. Use: systemctl restart noranx-bot"
  echo "Production uses systemd — do not run start.sh while the service is active."
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -e . -q
fi

# Stop stale bot/webhook processes (port 8080 conflict)
pkill -f "python -m bot.main" 2>/dev/null || true
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8080/tcp 2>/dev/null || true
fi
sleep 1

if ! docker compose ps postgres 2>/dev/null | grep -q healthy; then
  echo "Starting postgres and redis..."
  docker compose up -d postgres redis
  sleep 3
fi

# Load .env safely (handles spaces/Unicode in values; bot also reads .env via pydantic)
eval "$(.venv/bin/python - <<'PY'
from dotenv import dotenv_values
import shlex
for key, value in dotenv_values(".env").items():
    if value is not None:
        print(f"export {key}={shlex.quote(str(value))}")
PY
)"
.venv/bin/alembic upgrade head 2>/dev/null || true
.venv/bin/python scripts/seed_plans.py 2>/dev/null || true

echo "Starting bot..."
exec .venv/bin/python -m bot.main
