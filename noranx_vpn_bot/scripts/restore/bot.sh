#!/usr/bin/env bash
# Restore bot database, redis, source, env.
restore_bot() {
  local staging="$1"
  local dry_run="${2:-0}"
  local target_ip="${3:-}"
  local bot="$staging/bot"

  if [[ ! -d "$bot" ]]; then
    log_err "[bot] No bot backup in archive"
    return 1
  fi

  if [[ -f "$bot/project/source.tar" ]]; then
    log_info "[bot] Extracting project source..."
    if [[ "$dry_run" -eq 0 ]]; then
      tar -xf "$bot/project/source.tar" -C "$BOT_ROOT"
    fi
  fi

  if [[ -f "$bot/config/alembic.ini" ]]; then
    log_info "[bot] Restoring alembic.ini..."
    if [[ "$dry_run" -eq 0 ]]; then
      cp -a "$bot/config/alembic.ini" "$BOT_ROOT/alembic.ini"
    fi
  fi

  if [[ -f "$bot/config/.env" ]]; then
    log_info "[bot] Restoring .env..."
    if [[ "$dry_run" -eq 1 ]]; then
      cp -a "$bot/config/.env" "$BOT_ROOT/.env.restored-preview"
      log_info "[bot] Preview written to $BOT_ROOT/.env.restored-preview"
    else
      cp -a "$bot/config/.env" "$BOT_ROOT/.env"
    fi

    if [[ -n "$target_ip" && "$dry_run" -eq 0 ]]; then
      local old_ip
      old_ip="$(read_manifest_value "$staging" public_ip 2>/dev/null || echo "")"
      if [[ -n "$old_ip" && "$old_ip" != "unknown" && "$old_ip" != "$target_ip" ]]; then
        log_info "[bot] Replacing IP in .env: $old_ip -> $target_ip"
        sed -i "s/${old_ip}/${target_ip}/g" "$BOT_ROOT/.env" || true
      fi
    fi
  fi

  if [[ "$dry_run" -eq 1 ]]; then
    log_info "[bot] Dry-run: skipping database/redis restore"
    return 0
  fi

  log_info "[bot] Starting postgres/redis..."
  (cd "$BOT_ROOT" && docker compose up -d postgres redis)
  sleep 5
  init_stack_paths

  if [[ -z "${POSTGRES_CONTAINER:-}" ]]; then
    log_err "[bot] Postgres container not available after compose up"
    return 1
  fi

  if [[ -f "$bot/database/noranx_bot.dump" ]]; then
    log_info "[bot] Restoring PostgreSQL (pg_restore)..."
    docker cp "$bot/database/noranx_bot.dump" "$POSTGRES_CONTAINER:/tmp/noranx_bot.dump"
    docker exec "$POSTGRES_CONTAINER" pg_restore -U "$PG_USER" -d "$PG_DB" --clean --if-exists --no-owner /tmp/noranx_bot.dump \
      || log_warn "[bot] pg_restore reported warnings (may be OK on empty DB)"
    docker exec "$POSTGRES_CONTAINER" rm -f /tmp/noranx_bot.dump
  fi

  if [[ -f "$bot/redis/dump.rdb" && -n "${REDIS_CONTAINER:-}" ]]; then
    log_info "[bot] Restoring Redis..."
    docker compose -f "$BOT_ROOT/docker-compose.yml" stop redis >/dev/null 2>&1 || true
    docker cp "$bot/redis/dump.rdb" "$REDIS_CONTAINER:/data/dump.rdb"
    docker compose -f "$BOT_ROOT/docker-compose.yml" start redis >/dev/null 2>&1 || true
  fi

  log_info "[bot] Python venv + migrations..."
  if [[ ! -d "$BOT_ROOT/.venv" ]]; then
    python3 -m venv "$BOT_ROOT/.venv"
  fi
  "$BOT_ROOT/.venv/bin/pip" install -e "$BOT_ROOT" -q
  (cd "$BOT_ROOT" && "$BOT_ROOT/.venv/bin/alembic" upgrade head) || log_warn "[bot] alembic upgrade warnings"
}
