#!/usr/bin/env bash
# Restore Marzban from staging.
restore_marzban() {
  local staging="$1"
  local dry_run="${2:-0}"
  local mz="$staging/marzban"

  if [[ ! -d "$mz" ]]; then
    log_warn "[marzban] No marzban backup in archive — skip"
    return 0
  fi

  if [[ "$dry_run" -eq 1 ]]; then
    log_info "[marzban] Dry-run: would restore $MARZBAN_DATA"
    return 0
  fi

  if [[ -d "$MARZBAN_OPT" ]]; then
    log_info "[marzban] Stopping Marzban..."
    marzban_compose down >/dev/null 2>&1 || true
  fi

  log_info "[marzban] Restoring data..."
  rm -rf "$MARZBAN_DATA"
  mkdir -p "$(dirname "$MARZBAN_DATA")"
  tar -xzf "$mz/data.tar.gz" -C "$(dirname "$MARZBAN_DATA")"

  mkdir -p "$MARZBAN_OPT"
  if [[ -f "$mz/opt.env" ]]; then
    cp -a "$mz/opt.env" "$MARZBAN_OPT/.env"
  fi
  if [[ -f "$mz/opt.docker-compose.yml" ]]; then
    cp -a "$mz/opt.docker-compose.yml" "$MARZBAN_OPT/docker-compose.yml"
  fi

  ensure_iran_dat_mount

  log_info "[marzban] Starting Marzban..."
  marzban_compose up -d

  if wait_marzban_ready 30; then
    log_info "[marzban] Dashboard reachable on :18000"
  else
    log_err "[marzban] Dashboard not ready after restore"
    return 1
  fi
}
