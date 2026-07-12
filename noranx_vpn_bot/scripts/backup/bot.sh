#!/usr/bin/env bash
# Backup bot: PostgreSQL, Redis, config, source, logs.
backup_bot() {
  local staging="$1"
  local skip_logs="${2:-0}"
  local bot_dir="$staging/bot"

  mkdir -p "$bot_dir"/{database,redis,config,project,logs}

  log_info "[bot] PostgreSQL dump..."
  if [[ -z "${POSTGRES_CONTAINER:-}" ]]; then
    log_err "[bot] Postgres container not found"
    return 1
  fi
  docker exec "$POSTGRES_CONTAINER" pg_dump -U "$PG_USER" -d "$PG_DB" --format=custom --file=/tmp/noranx_bot.dump
  docker cp "$POSTGRES_CONTAINER:/tmp/noranx_bot.dump" "$bot_dir/database/noranx_bot.dump"
  docker exec "$POSTGRES_CONTAINER" rm -f /tmp/noranx_bot.dump
  docker exec "$POSTGRES_CONTAINER" pg_dump -U "$PG_USER" -d "$PG_DB" --format=plain --no-owner --no-acl \
    > "$bot_dir/database/noranx_bot.sql"

  log_info "[bot] Redis snapshot..."
  if [[ -n "${REDIS_CONTAINER:-}" ]]; then
    if docker exec "$REDIS_CONTAINER" redis-cli BGSAVE >/dev/null 2>&1; then
      sleep 1
    fi
    if docker cp "$REDIS_CONTAINER:/data/dump.rdb" "$bot_dir/redis/dump.rdb" 2>/dev/null; then
      :
    elif docker exec "$REDIS_CONTAINER" redis-cli --rdb /tmp/dump.rdb >/dev/null 2>&1 \
      && docker cp "$REDIS_CONTAINER:/tmp/dump.rdb" "$bot_dir/redis/dump.rdb" 2>/dev/null; then
      :
    else
      log_warn "[bot] Redis RDB copy skipped (non-critical)"
    fi
  else
    log_warn "[bot] Redis container not found"
  fi

  log_info "[bot] Config files..."
  cp -a "$BOT_ROOT/.env" "$bot_dir/config/.env" 2>/dev/null || true
  cp -a "$BOT_ROOT/.env.example" "$bot_dir/config/.env.example" 2>/dev/null || true
  cp -a "$BOT_ROOT/alembic.ini" "$bot_dir/config/" 2>/dev/null || true

  log_info "[bot] Project source..."
  tar -C "$BOT_ROOT" -cf "$bot_dir/project/source.tar" \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='backups' \
    --exclude='.git' \
    --exclude='logs/*.log' \
    bot webhooks alembic scripts infrastructure docker-compose.yml pyproject.toml README.md Dockerfile .env.example pytest.ini tests 2>/dev/null \
    || tar -C "$BOT_ROOT" -cf "$bot_dir/project/source.tar" bot webhooks alembic scripts infrastructure docker-compose.yml pyproject.toml

  if [[ "$skip_logs" -eq 0 && -d "$BOT_ROOT/logs" ]]; then
    log_info "[bot] Logs..."
    tar -C "$BOT_ROOT" -cf "$bot_dir/logs/bot-logs.tar" logs 2>/dev/null || true
  fi
}
