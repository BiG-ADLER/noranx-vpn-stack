#!/usr/bin/env bash
# Gated IP limiter + sub routing audit — exits non-zero on failure.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${ROOT}/logs/limiter-audit-$(date +%Y%m%d).txt"
REQUIRE_IP_TRAFFIC=false
for arg in "$@"; do
  case "$arg" in
    --require-ip-traffic) REQUIRE_IP_TRAFFIC=true ;;
  esac
done
mkdir -p "${ROOT}/logs"

{
  echo "=== Limiter audit $(date -Iseconds) ==="
  echo ""
  echo "--- Containers ---"
  docker ps -a --filter name=marzneshiniplimit --format 'table {{.Names}}\t{{.Status}}'
  echo ""
  echo "--- Device limiter (retired) ---"
  if docker ps -a --format '{{.Names}}' | grep -q noranx-device-limiter; then
    echo "WARN: noranx-device-limiter container still present"
  else
    echo "device limiter: not running (expected)"
  fi
  if ss -tlnp 2>/dev/null | grep -q ':3000 '; then
    echo "FAIL: port 3000 still listening"
    exit 1
  fi
  echo "port 3000: closed (expected)"
  echo ""
  echo "--- IP limiter :6284 ---"
  curl -sf "http://127.0.0.1:6284/health" | grep -q '"status"'
  echo "ip health: OK"
  echo ""
  echo "--- IP limiter worker ---"
  docker exec marzneshiniplimit ps aux | grep -q '[p]ython marzneshiniplimit.py'
  echo "marzneshiniplimit.py: running"
  echo ""
  echo "--- IP limiter active ips smoke ---"
  IP_COUNTS=$(docker exec marzneshiniplimit grep 'Number of all active ips' /marzneshiniplimitcode/app.log 2>/dev/null | tail -5 | sed 's/.*: //' || true)
  echo "last 5 active ip counts: ${IP_COUNTS:-none}"
  if [[ "$REQUIRE_IP_TRAFFIC" == true ]]; then
    if [[ -z "$IP_COUNTS" ]] || echo "$IP_COUNTS" | grep -qv '[1-9]'; then
      echo "FAIL: --require-ip-traffic set but no non-zero active ip counts in recent logs"
      exit 1
    fi
    echo "active ip traffic: OK"
  else
    echo "active ip traffic: skipped (use --require-ip-traffic to enforce)"
  fi
  echo ""
  echo "--- nginx /sub/ routing (direct to Marzban) ---"
  grep -A2 'location /sub/' /etc/nginx/sites-enabled/sub.ibaxgames.ir.conf | head -6
  if grep -q '127.0.0.1:3000' /etc/nginx/sites-enabled/sub.ibaxgames.ir.conf 2>/dev/null; then
    echo "FAIL: sub.ibaxgames.ir still proxies to device limiter :3000"
    exit 1
  fi
  if ! grep -q '127.0.0.1:18000' /etc/nginx/sites-enabled/sub.ibaxgames.ir.conf 2>/dev/null; then
    echo "FAIL: sub.ibaxgames.ir does not proxy to Marzban :18000"
    exit 1
  fi
  echo "sub nginx: OK (Marzban direct)"
  echo ""
  echo "--- Bot health_check ---"
} | tee -a "$LOG"

cd "$ROOT"
.venv/bin/python scripts/health_check.py --plan device_1 --skip-provision 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "=== Audit passed ===" | tee -a "$LOG"
