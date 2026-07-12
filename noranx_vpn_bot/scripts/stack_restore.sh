#!/usr/bin/env bash
# Full stack restore from noranx-stack archive.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/stack_common.sh
source "$SCRIPT_DIR/lib/stack_common.sh"
# shellcheck source=restore/preflight.sh
source "$SCRIPT_DIR/restore/preflight.sh"
# shellcheck source=restore/safety.sh
source "$SCRIPT_DIR/restore/safety.sh"
# shellcheck source=restore/marzban.sh
source "$SCRIPT_DIR/restore/marzban.sh"
# shellcheck source=restore/bot.sh
source "$SCRIPT_DIR/restore/bot.sh"
# shellcheck source=restore/infrastructure.sh
source "$SCRIPT_DIR/restore/infrastructure.sh"
# shellcheck source=restore/validate.sh
source "$SCRIPT_DIR/restore/validate.sh"

ARCHIVE=""
TARGET_IP=""
SKIP_DNS=0
SKIP_TLS=0
DRY_RUN=0
SKIP_VALIDATE=0
EXTRACT_ROOT=""

usage() {
  cat <<EOF
Usage: $(basename "$0") ARCHIVE.tar.gz [OPTIONS]

Options:
  --target-ip IP   Replace old public IP in restored .env
  --skip-dns       Skip DNS verify/update
  --skip-tls       Skip Let's Encrypt restore
  --skip-validate  Skip post-restore validation
  --dry-run        Preflight + preview only (no destructive changes)
  -h, --help       Show this help

Environment: BOT_ROOT, MARZBAN_DATA, MARZBAN_OPT, RESTORE_SAFETY_ROOT
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-ip) TARGET_IP="$2"; shift 2 ;;
    --skip-dns) SKIP_DNS=1; shift ;;
    --skip-tls) SKIP_TLS=1; shift ;;
    --skip-validate) SKIP_VALIDATE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) log_err "Unknown option: $1"; usage; exit 1 ;;
    *)
      if [[ -z "$ARCHIVE" ]]; then
        ARCHIVE="$1"
      else
        log_err "Unexpected argument: $1"
        usage
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$ARCHIVE" ]]; then
  usage
  exit 1
fi

[[ "$ARCHIVE" != /* ]] && ARCHIVE="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"

init_stack_paths
TS="$(utc_timestamp)"
EXTRACT_ROOT="$(mktemp -d /tmp/noranx-restore-XXXXXX)"

trap 'rm -rf "$EXTRACT_ROOT"' EXIT

log_info "=== NoranX stack restore ($TS) ==="
restore_preflight "$ARCHIVE" "$EXTRACT_ROOT"
STAGING="$RESTORE_STAGING"

if [[ "$DRY_RUN" -eq 1 ]]; then
  log_info "Dry-run: manifest hostname=$(read_manifest_value "$STAGING" hostname)"
  log_info "Dry-run: manifest public_ip=$(read_manifest_value "$STAGING" public_ip)"
  restore_marzban "$STAGING" 1
  restore_bot "$STAGING" 1 "$TARGET_IP"
  restore_infrastructure "$STAGING" 1 "$SKIP_TLS"
  log_info "Dry-run complete — no changes applied"
  exit 0
fi

restore_safety_snapshot "$TS"
restore_marzban "$STAGING" 0
restore_bot "$STAGING" 0 "$TARGET_IP"
restore_infrastructure "$STAGING" 0 "$SKIP_TLS"

log_info "Starting bot via start.sh..."
mkdir -p "$BOT_ROOT/logs"
nohup bash "$BOT_ROOT/scripts/start.sh" >"$BOT_ROOT/logs/stack-restore-start.log" 2>&1 &
sleep 12

if [[ "$SKIP_VALIDATE" -eq 0 ]]; then
  restore_validate "$STAGING" "$SKIP_DNS" "$TARGET_IP" || {
    log_err "Validation failed. Safety snapshot: $(cat "$RESTORE_SAFETY_ROOT/latest-pre.txt" 2>/dev/null || echo unknown)"
    exit 1
  }
fi

log_info "Restore complete."
