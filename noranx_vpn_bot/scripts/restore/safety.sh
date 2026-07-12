#!/usr/bin/env bash
# Safety snapshot before restore.
restore_safety_snapshot() {
  local ts="$1"
  local dest="$RESTORE_SAFETY_ROOT/pre-$ts"
  mkdir -p "$dest"

  log_info "[safety] Snapshot -> $dest"

  if [[ -d "$MARZBAN_DATA" ]]; then
    mkdir -p "$dest/marzban"
    tar -czf "$dest/marzban/data.tar.gz" -C "$(dirname "$MARZBAN_DATA")" "$(basename "$MARZBAN_DATA")"
  fi

  if [[ -d "$MARZBAN_OPT" ]]; then
    mkdir -p "$dest/marzban-opt"
    cp -a "$MARZBAN_OPT/.env" "$dest/marzban-opt/.env" 2>/dev/null || true
    cp -a "$MARZBAN_OPT/docker-compose.yml" "$dest/marzban-opt/docker-compose.yml" 2>/dev/null || true
  fi

  if [[ -f "$BOT_ROOT/.env" ]]; then
    mkdir -p "$dest/bot"
    cp -a "$BOT_ROOT/.env" "$dest/bot/.env"
  fi

  if [[ -f "$DEVICE_LIMITER_DIR/.env" ]]; then
    mkdir -p "$dest/infrastructure"
    cp -a "$DEVICE_LIMITER_DIR/.env" "$dest/infrastructure/device-limiter.env"
  fi

  if [[ -f "$IP_LIMITER_CONFIG" ]]; then
    mkdir -p "$dest/infrastructure"
    cp -a "$IP_LIMITER_CONFIG" "$dest/infrastructure/ip-limiter.config.json"
  fi

  echo "$dest" > "$RESTORE_SAFETY_ROOT/latest-pre.txt"
  log_info "[safety] Rollback hint: restore from $dest"
}
