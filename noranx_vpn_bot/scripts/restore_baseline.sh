#!/usr/bin/env bash
# Phase 0: pre-restore baseline snapshot
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$ROOT/logs/restore-baseline-$TS.txt"
EXPECTED_IP="${EXPECTED_IP:-5.75.201.19}"
BACKUP_MZ="$ROOT/extracted/marzban/marzban_data/db.sqlite3"
BACKUP_BOT="$ROOT/extracted/bot/staging-20260612T215059Z/database/noranx_bot.dump"

mkdir -p "$ROOT/logs" /root/restore-safety/certs

{
  echo "=== RESTORE BASELINE $TS ==="
  echo "expected_ip=$EXPECTED_IP"
  echo ""
  echo "--- Public IP ---"
  curl -4 -s ifconfig.me || true
  echo ""
  hostname -I 2>/dev/null || true
  echo ""
  echo "--- Docker ---"
  docker ps -a 2>/dev/null || echo "docker unavailable"
  echo ""
  echo "--- Listening ports ---"
  ss -tlnp 2>/dev/null | grep -E ':18000|:8000|:443|:3000|:6284|:8080|:5433|:6380' || true
  echo ""
  echo "--- DNS ---"
  for h in sub.ibaxgames.ir panel.bigadler.xyz de.bigadler.xyz bot.bigadler.xyz; do
    echo -n "$h -> "
    dig +short A "$h" @1.1.1.1 | head -1
  done
  echo ""
  echo "--- Current Marzban DB ---"
  if [[ -f /var/lib/marzban/db.sqlite3 ]]; then
    python3 - <<'PY'
import sqlite3
con = sqlite3.connect("/var/lib/marzban/db.sqlite3")
cur = con.cursor()
cur.execute("SELECT COUNT(*) FROM users")
print("users", cur.fetchone()[0])
con.close()
PY
  else
    echo "no /var/lib/marzban/db.sqlite3"
  fi
  echo ""
  echo "--- Backup inventory ---"
  ls -lah "$BACKUP_MZ" "$BACKUP_BOT" 2>/dev/null || true
  echo ""
  echo "--- Backup Marzban users ---"
  python3 - <<PY
import sqlite3
con = sqlite3.connect("$BACKUP_MZ")
cur = con.cursor()
cur.execute("SELECT COUNT(*) FROM users")
print("backup_users", cur.fetchone()[0])
con.close()
PY
  echo ""
  echo "--- Prerequisites ---"
  [[ -f "$BACKUP_MZ" ]] && echo "OK: marzban backup db" || echo "FAIL: marzban backup db missing"
  [[ -f "$BACKUP_BOT" ]] && echo "OK: bot backup dump" || echo "FAIL: bot backup dump missing"
  [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]] && echo "OK: CLOUDFLARE_API_TOKEN set" || echo "WARN: CLOUDFLARE_API_TOKEN not set"
  echo ""
  echo "=== BASELINE COMPLETE ==="
} | tee "$LOG"

echo "Log: $LOG"
