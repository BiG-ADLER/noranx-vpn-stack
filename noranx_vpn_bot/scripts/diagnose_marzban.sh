#!/usr/bin/env bash
# Quick Marzban + limiter connectivity diagnostics (run from noranx_vpn_bot root)
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

MARZBAN_URL="${MARZBAN_URL:-https://127.0.0.1:8000}"
MARZBAN_USER="${MARZBAN_USER:-}"
MARZBAN_PASS="${MARZBAN_PASS:-}"

echo "=== NoranX Marzban Diagnostics ==="
echo "MARZBAN_URL=$MARZBAN_URL"
echo

echo "--- HTTP on :8000 (expect failure if Marzban is TLS-only) ---"
curl -sS -m 5 -o /dev/null -w "http://127.0.0.1:8000 → %{http_code} (%{errormsg})\n" \
  http://127.0.0.1:8000/api/system 2>&1 || true

echo "--- HTTPS on :8000 (expect 401/403 without token) ---"
curl -sk -m 5 -o /dev/null -w "https://127.0.0.1:8000 → %{http_code}\n" \
  https://127.0.0.1:8000/api/system 2>&1 || true

if [[ -n "$MARZBAN_USER" && -n "$MARZBAN_PASS" ]]; then
  echo "--- Token request ---"
  TOKEN_RESP=$(curl -sk -m 10 -X POST "https://127.0.0.1:8000/api/admin/token" \
    -d "username=${MARZBAN_USER}&password=${MARZBAN_PASS}" 2>&1) || true
  if echo "$TOKEN_RESP" | grep -q access_token; then
    echo "Token: OK"
  else
    echo "Token: FAIL — $TOKEN_RESP"
  fi
fi

echo
echo "--- Local service ports ---"
for port in 3000 6284 8080; do
  if ss -tln | grep -q ":${port} "; then
    echo "port $port: LISTEN"
  else
    echo "port $port: closed"
  fi
done

echo
echo "--- Docker containers ---"
docker ps --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null | grep -iE 'marzban|miplimiter|device|limiter' || echo "(no matching containers)"

echo
echo "--- Python health_check ---"
.venv/bin/python scripts/health_check.py --no-cleanup 2>&1 || true
