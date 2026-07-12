#!/usr/bin/env bash
# Backup Marzban data and /opt/marzban config.
backup_marzban() {
  local staging="$1"
  local dry_run="${2:-0}"
  local mz_dir="$staging/marzban"
  mkdir -p "$mz_dir"

  if [[ ! -d "$MARZBAN_DATA" ]]; then
    log_err "[marzban] Data directory missing: $MARZBAN_DATA"
    return 1
  fi

  local stopped=0
  if [[ "$dry_run" -eq 0 && -d "$MARZBAN_OPT" ]]; then
    log_info "[marzban] Stopping Marzban for consistent snapshot..."
    if marzban_compose stop >/dev/null 2>&1; then
      stopped=1
    fi
  fi

  log_info "[marzban] Archiving $MARZBAN_DATA..."
  tar -czf "$mz_dir/data.tar.gz" -C "$(dirname "$MARZBAN_DATA")" "$(basename "$MARZBAN_DATA")"

  if [[ -f "$MARZBAN_OPT/.env" ]]; then
    cp -a "$MARZBAN_OPT/.env" "$mz_dir/opt.env"
  else
    log_warn "[marzban] Missing $MARZBAN_OPT/.env"
  fi

  if [[ -f "$MARZBAN_OPT/docker-compose.yml" ]]; then
    cp -a "$MARZBAN_OPT/docker-compose.yml" "$mz_dir/opt.docker-compose.yml"
  else
    log_warn "[marzban] Missing $MARZBAN_OPT/docker-compose.yml"
  fi

  if [[ "$stopped" -eq 1 ]]; then
    log_info "[marzban] Starting Marzban..."
    marzban_compose up -d >/dev/null 2>&1 || log_warn "[marzban] Failed to restart Marzban"
  fi
}
