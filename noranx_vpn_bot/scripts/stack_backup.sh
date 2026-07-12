#!/usr/bin/env bash
# Full stack backup: bot + Marzban + infrastructure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/stack_common.sh
source "$SCRIPT_DIR/lib/stack_common.sh"
# shellcheck source=backup/bot.sh
source "$SCRIPT_DIR/backup/bot.sh"
# shellcheck source=backup/marzban.sh
source "$SCRIPT_DIR/backup/marzban.sh"
# shellcheck source=backup/infrastructure.sh
source "$SCRIPT_DIR/backup/infrastructure.sh"

OUTPUT_DIR=""
SKIP_LOGS=0
SKIP_TLS=0
BOT_ONLY=0
DRY_RUN=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --output DIR     Backup directory (default: \$BACKUP_ROOT)
  --skip-logs      Omit bot log archive
  --skip-tls       Omit Let's Encrypt certificates
  --bot-only       Backup bot component only (legacy mode)
  --dry-run        Preflight + staging layout only (no Marzban stop, no archive)
  -h, --help       Show this help

Environment: BOT_ROOT, MARZBAN_DATA, MARZBAN_OPT, BACKUP_ROOT, POSTGRES_CONTAINER
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) OUTPUT_DIR="$2"; shift 2 ;;
    --skip-logs) SKIP_LOGS=1; shift ;;
    --skip-tls) SKIP_TLS=1; shift ;;
    --bot-only) BOT_ONLY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) log_err "Unknown option: $1"; usage; exit 1 ;;
  esac
done

require_root
require_commands docker tar sha256sum python3 curl
init_stack_paths

TS="$(utc_timestamp)"
BACKUP_ROOT="${OUTPUT_DIR:-$BACKUP_ROOT}"
STAGING="$BACKUP_ROOT/staging-$TS"
ARCHIVE="$BACKUP_ROOT/noranx-stack-$TS.tar.gz"

secrets_warning

log_info "=== NoranX stack backup ($TS) ==="
log_info "BOT_ROOT=$BOT_ROOT"
log_info "MARZBAN_DATA=$MARZBAN_DATA"
log_info "POSTGRES_CONTAINER=${POSTGRES_CONTAINER:-none}"

mkdir -p "$STAGING/meta"

if [[ -z "${POSTGRES_CONTAINER:-}" ]]; then
  log_err "Postgres container not running. Start bot stack first: docker compose up -d postgres redis"
  exit 1
fi

if [[ "$BOT_ONLY" -eq 0 && ! -d "$MARZBAN_DATA" ]]; then
  log_err "Marzban data dir missing: $MARZBAN_DATA"
  exit 1
fi

backup_bot "$STAGING" "$SKIP_LOGS"

if [[ "$BOT_ONLY" -eq 0 ]]; then
  backup_marzban "$STAGING" "$DRY_RUN"
  backup_infrastructure "$STAGING" "$SKIP_TLS"
fi

log_info "Collecting metadata..."
echo "$(hostname)" > "$STAGING/meta/hostname.txt"
public_ip > "$STAGING/meta/public_ip.txt"
docker ps -a > "$STAGING/meta/docker_ps.txt" 2>/dev/null || true
collect_table_counts "$STAGING/meta/table_counts.txt"

write_manifest_json "$STAGING" "$TS" "$(basename "$ARCHIVE")"
write_checksums "$STAGING"

if [[ "$DRY_RUN" -eq 1 ]]; then
  log_info "Dry-run complete. Staging kept at: $STAGING"
  exit 0
fi

mkdir -p "$BACKUP_ROOT"
log_info "Packing archive..."
tar -czf "$ARCHIVE" -C "$BACKUP_ROOT" "staging-$TS"
chmod 600 "$ARCHIVE"
rm -rf "$STAGING"

SIZE="$(du -h "$ARCHIVE" | cut -f1)"
log_info "Backup complete: $ARCHIVE ($SIZE)"
log_info "Restore: $SCRIPT_DIR/stack_restore.sh $ARCHIVE"
