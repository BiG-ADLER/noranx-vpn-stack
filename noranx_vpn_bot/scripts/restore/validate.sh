#!/usr/bin/env bash
# Post-restore validation gate.
restore_validate() {
  local staging="${1:-}"
  local skip_dns="${2:-0}"
  local target_ip="${3:-}"
  local log="$BOT_ROOT/logs/stack-restore-validation-$(utc_timestamp).txt"
  local fail=0

  mkdir -p "$BOT_ROOT/logs"

  log_line() {
    echo "$1" | tee -a "$log"
  }

  check() {
    local name="$1"
    local cmd="$2"
    if eval "$cmd" >>"$log" 2>&1; then
      log_line "OK: $name"
    else
      log_line "FAIL: $name"
      fail=$((fail + 1))
    fi
  }

  log_line "=== STACK RESTORE VALIDATION ==="

  check "marzban internal" \
    "curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:18000/dashboard/ | grep -qE '200|302'"

  if [[ -n "$staging" && -f "$staging/MANIFEST.json" ]]; then
    local min_users
    min_users="$(python3 - <<PY
import json
from pathlib import Path
m = json.loads(Path("$staging/MANIFEST.json").read_text())
users = m.get("counts", {}).get("users", "0")
try:
    print(int(users))
except ValueError:
    print(1)
PY
)"
    check "marzban users>=$min_users" \
      "python3 -c \"import sqlite3; assert sqlite3.connect('$MARZBAN_DATA/db.sqlite3').execute('select count(*) from users').fetchone()[0] >= $min_users\""
  fi

  check "bot health local" \
    "curl -sf http://127.0.0.1:8080/health | grep -q ok"

  if curl -sf http://127.0.0.1:8080/ready >/dev/null 2>&1; then
  ready_ms="$(curl -sf -o /dev/null -w '%{time_total}' http://127.0.0.1:8080/ready 2>/dev/null || echo 0)"
  log_line "OK: bot ready probe (${ready_ms}s)"
  else
  log_line "WARN: bot /ready probe failed (non-fatal)"
  fi

  check "ip limiter" \
    "curl -sf http://127.0.0.1:6284/health | grep -q ok"

  check "device limiter retired" \
    "! ss -tlnp 2>/dev/null | grep -q ':3000 '"

  check "sub path not 502" \
    "code=\$(curl -sk -o /dev/null -w '%{http_code}' -H 'X-HWID: val_gate' https://sub.ibaxgames.ir/sub/TESTTOKEN); test \"\$code\" != 502"

  if [[ "$skip_dns" -eq 0 ]]; then
    TARGET_IP="${target_ip:-$(public_ip)}" \
      bash "$BOT_ROOT/scripts/restore_update_dns.sh" >>"$log" 2>&1 \
      || { log_line "WARN: DNS check/update issues"; fail=$((fail + 1)); }
  fi

  if [[ -x "$BOT_ROOT/.venv/bin/python" ]]; then
    (cd "$BOT_ROOT" && .venv/bin/python scripts/bot_telegram_check.py) >>"$log" 2>&1 \
      && log_line "OK: bot_telegram_check.py" \
      || { log_line "FAIL: bot_telegram_check.py"; fail=$((fail + 1)); }
  fi

  if [[ -x "$BOT_ROOT/.venv/bin/python" ]]; then
    (cd "$BOT_ROOT" && MARZBAN_DRY_RUN=false .venv/bin/python scripts/health_check.py --skip-provision) >>"$log" 2>&1 \
      && log_line "OK: health_check.py" \
      || { log_line "FAIL: health_check.py"; fail=$((fail + 1)); }
  fi

  log_line "=== failures=$fail ==="
  log_line "Log: $log"
  return "$fail"
}
