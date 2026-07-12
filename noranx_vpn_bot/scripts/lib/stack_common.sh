#!/usr/bin/env bash
# Shared helpers for stack backup/restore.
set -euo pipefail

STACK_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_SCRIPTS_DIR="$(cd "$STACK_LIB_DIR/.." && pwd)"
BOT_ROOT="${BOT_ROOT:-$(cd "$STACK_SCRIPTS_DIR/.." && pwd)}"
BACKUP_ROOT="${BACKUP_ROOT:-$BOT_ROOT/backups}"
MARZBAN_DATA="${MARZBAN_DATA:-/var/lib/marzban}"
MARZBAN_OPT="${MARZBAN_OPT:-/opt/marzban}"
DEVICE_LIMITER_DIR="${DEVICE_LIMITER_DIR:-$BOT_ROOT/infrastructure/device-limiter}"
IP_LIMITER_CONFIG="${IP_LIMITER_CONFIG:-/opt/marzneshiniplimit/config.json}"
NGINX_LIVE_DIR="${NGINX_LIVE_DIR:-/etc/nginx}"
RESTORE_SAFETY_ROOT="${RESTORE_SAFETY_ROOT:-/root/restore-safety}"
PG_USER="${PG_USER:-noranx}"
PG_DB="${PG_DB:-noranx_bot}"

TLS_DOMAINS=(
  sub.ibaxgames.ir
  panel.bigadler.xyz
  de.bigadler.xyz
  bot.bigadler.xyz
)

log_info() { echo "[INFO] $*"; }
log_warn() { echo "[WARN] $*" >&2; }
log_err()  { echo "[ERROR] $*" >&2; }

secrets_warning() {
  cat <<'EOF'

*** SECURITY WARNING ***
This archive contains secrets: .env files, database dumps, TLS private keys,
Marzban credentials. Store offline with chmod 600. Do not commit to git.

EOF
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    log_err "This script must run as root."
    exit 1
  fi
}

require_commands() {
  local cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || { log_err "Required command not found: $cmd"; exit 1; }
  done
}

detect_docker_container() {
  local pattern="$1"
  docker ps --format '{{.Names}}' 2>/dev/null | grep -E "$pattern" | grep -E 'noranx_vpn_bot' | head -1 \
    || docker ps --format '{{.Names}}' 2>/dev/null | grep -E "$pattern" | head -1 \
    || true
}

init_stack_paths() {
  POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-$(detect_docker_container 'postgres')}"
  REDIS_CONTAINER="${REDIS_CONTAINER:-$(detect_docker_container 'redis')}"
  DEVICE_LIMITER_CONTAINER="${DEVICE_LIMITER_CONTAINER:-$(detect_docker_container 'device-limiter|noranx-device-limiter')}"
  IP_LIMITER_CONTAINER="${IP_LIMITER_CONTAINER:-$(detect_docker_container 'marzneshiniplimit|ip-limiter')}"
  MARZBAN_CONTAINER="${MARZBAN_CONTAINER:-$(detect_docker_container 'marzban')}"
}

utc_timestamp() {
  date -u +%Y%m%dT%H%M%SZ
}

public_ip() {
  curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || curl -4 -s --max-time 5 icanhazip.com 2>/dev/null || echo "unknown"
}

write_checksums() {
  local root="$1"
  (
    cd "$root"
    find . -type f ! -name 'CHECKSUMS.sha256' -print0 \
      | sort -z \
      | xargs -0 sha256sum
  ) > "$root/CHECKSUMS.sha256"
}

verify_checksums() {
  local root="$1"
  if [[ ! -f "$root/CHECKSUMS.sha256" ]]; then
    log_err "CHECKSUMS.sha256 missing in $root"
    return 1
  fi
  (cd "$root" && sha256sum -c CHECKSUMS.sha256)
}

collect_table_counts() {
  local out="$1"
  {
    echo "# postgres"
    if [[ -n "${POSTGRES_CONTAINER:-}" ]]; then
      docker exec "$POSTGRES_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -t -c "
        SELECT relname || '=' || n_live_tup
        FROM pg_stat_user_tables ORDER BY relname;
      " 2>/dev/null || echo "postgres=unavailable"
    else
      echo "postgres=container_not_found"
    fi
    echo "# marzban"
    if [[ -f "$MARZBAN_DATA/db.sqlite3" ]]; then
      python3 - <<PY
import sqlite3
con = sqlite3.connect("$MARZBAN_DATA/db.sqlite3")
cur = con.cursor()
for table in ("users", "nodes", "hosts"):
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"{table}={cur.fetchone()[0]}")
    except Exception:
        print(f"{table}=error")
con.close()
PY
    else
      echo "marzban_db=missing"
    fi
  } > "$out"
}

write_manifest_json() {
  local staging="$1"
  local ts="$2"
  local archive_name="$3"
  python3 - <<PY
import json
import os
from pathlib import Path

staging = Path("$staging")
meta = staging / "meta"
counts = {}
if (meta / "table_counts.txt").exists():
    for line in (meta / "table_counts.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            counts[k] = v

manifest = {
    "backup_time_utc": "$ts",
    "archive_name": "$archive_name",
    "hostname": (meta / "hostname.txt").read_text().strip() if (meta / "hostname.txt").exists() else "",
    "public_ip": (meta / "public_ip.txt").read_text().strip() if (meta / "public_ip.txt").exists() else "",
    "paths": {
        "bot_root": "$BOT_ROOT",
        "marzban_data": "$MARZBAN_DATA",
        "marzban_opt": "$MARZBAN_OPT",
    },
    "components": {
        "bot": (staging / "bot").exists(),
        "marzban": (staging / "marzban").exists(),
        "infrastructure": (staging / "infrastructure").exists(),
    },
    "counts": counts,
    "files": [],
}

for path in sorted(staging.rglob("*")):
    if path.is_file() and path.name not in ("MANIFEST.json", "CHECKSUMS.sha256"):
        rel = str(path.relative_to(staging))
        manifest["files"].append({"path": rel, "size": path.stat().st_size})

(staging / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY
}

read_manifest_value() {
  local staging="$1"
  local key="$2"
  python3 - <<PY
import json
from pathlib import Path
m = json.loads(Path("$staging/MANIFEST.json").read_text())
keys = "$key".split(".")
v = m
for k in keys:
    v = v[k]
print(v)
PY
}

marzban_compose() {
  if [[ -f "$MARZBAN_OPT/docker-compose.yml" ]]; then
    (cd "$MARZBAN_OPT" && docker compose "$@")
  else
    log_warn "Marzban compose not found at $MARZBAN_OPT"
    return 1
  fi
}

wait_marzban_ready() {
  local tries="${1:-30}"
  local i
  for ((i = 1; i <= tries; i++)); do
    if curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:18000/dashboard/ 2>/dev/null | grep -qE '200|302'; then
      return 0
    fi
    sleep 2
  done
  return 1
}

ensure_iran_dat_mount() {
  local compose="$MARZBAN_OPT/docker-compose.yml"
  [[ -f "$compose" ]] || return 0
  if grep -q 'iran.dat' "$compose"; then
    return 0
  fi
  log_warn "Adding iran.dat bind mount to Marzban docker-compose.yml"
  python3 - <<PY
from pathlib import Path
p = Path("$compose")
text = p.read_text()
needle = "volumes:"
if needle not in text:
    raise SystemExit("Could not patch docker-compose: no volumes section")
if "iran.dat" in text:
    raise SystemExit(0)
insert = "      - /var/lib/marzban/assets/iran.dat:/usr/local/share/xray/iran.dat:ro\n"
lines = text.splitlines(True)
out = []
for line in lines:
    out.append(line)
    if line.strip() == "- /var/lib/marzban:/var/lib/marzban":
        out.append(insert)
p.write_text("".join(out))
PY
}

backup_tls_certs() {
  local dest="$1"
  local tmp
  tmp="$(mktemp -d)"
  local found=0
  for domain in "${TLS_DOMAINS[@]}"; do
    if [[ -d "/etc/letsencrypt/live/$domain" ]]; then
      mkdir -p "$tmp/live/$domain" "$tmp/archive/$domain"
      cp -aL "/etc/letsencrypt/live/$domain/." "$tmp/live/$domain/" 2>/dev/null || true
      if [[ -d "/etc/letsencrypt/archive/$domain" ]]; then
        cp -a "/etc/letsencrypt/archive/$domain/." "$tmp/archive/$domain/" 2>/dev/null || true
      fi
      found=1
    fi
  done
  if [[ "$found" -eq 1 ]]; then
    tar -czf "$dest" -C "$tmp" .
  else
    log_warn "No Let's Encrypt certs found for configured domains"
    mkdir -p "$tmp/empty"
    tar -czf "$dest" -C "$tmp" empty
  fi
  rm -rf "$tmp"
}

restore_tls_certs() {
  local src="$1"
  [[ -f "$src" ]] || return 0
  mkdir -p /etc/letsencrypt
  tar -xzf "$src" -C /etc/letsencrypt
}
