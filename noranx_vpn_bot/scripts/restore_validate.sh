#!/usr/bin/env bash
# Post-restore validation gate (reads thresholds from MANIFEST when available).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="${MANIFEST:-}"

if [[ -z "$MANIFEST" ]]; then
  latest="$(ls -t "$ROOT/backups"/noranx-stack-*.tar.gz 2>/dev/null | head -1 || true)"
  if [[ -n "$latest" ]]; then
    tmp="$(mktemp -d)"
    tar -xzf "$latest" -C "$tmp" staging-*/MANIFEST.json 2>/dev/null || true
    MANIFEST="$(find "$tmp" -name MANIFEST.json | head -1 || true)"
  fi
fi

STAGING=""
if [[ -n "$MANIFEST" && -f "$MANIFEST" ]]; then
  STAGING="$(dirname "$MANIFEST")"
fi

# shellcheck source=lib/stack_common.sh
source "$SCRIPT_DIR/lib/stack_common.sh"
# shellcheck source=restore/validate.sh
source "$SCRIPT_DIR/restore/validate.sh"

init_stack_paths
TARGET_IP="${TARGET_IP:-$(public_ip)}"
SKIP_DNS="${SKIP_DNS:-0}"

restore_validate "$STAGING" "$SKIP_DNS" "$TARGET_IP"
