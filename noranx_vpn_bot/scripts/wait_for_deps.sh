#!/usr/bin/env bash
# Wait for core dependencies before starting the bot (post-reboot race guard).
set -euo pipefail

wait_url() {
  local name="$1"
  local url="$2"
  local max_attempts="${3:-90}"
  local i
  for ((i = 1; i <= max_attempts; i++)); do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "OK: $name ready (attempt $i)"
      return 0
    fi
    sleep 2
  done
  echo "WARN: $name not ready after $((max_attempts * 2))s" >&2
  return 1
}

# Marzban dashboard (TLS self-signed)
for i in $(seq 1 90); do
  if curl -skf "https://127.0.0.1:18000/dashboard/" >/dev/null 2>&1; then
    echo "OK: marzban ready (attempt $i)"
    break
  fi
  if [[ "$i" -eq 90 ]]; then
    echo "WARN: marzban not ready after 180s" >&2
  fi
  sleep 2
done

# IP limiter
wait_url "ip_limiter" "http://127.0.0.1:6284/health" 30 || true

exit 0
