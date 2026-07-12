#!/usr/bin/env bash
# Backup limiters, nginx, TLS, systemd unit.
backup_infrastructure() {
  local staging="$1"
  local skip_tls="${2:-0}"
  local infra_dir="$staging/infrastructure"
  mkdir -p "$infra_dir/systemd"

  log_info "[infra] Device limiter (archived — optional backup only)..."
  if [[ -f "$DEVICE_LIMITER_DIR/.env" ]]; then
    cp -a "$DEVICE_LIMITER_DIR/.env" "$infra_dir/device-limiter.env"
  else
    log_warn "[infra] Device limiter .env not found"
  fi

  local vol_name=""
  vol_name="$(docker volume ls --format '{{.Name}}' 2>/dev/null | grep -E 'device_limiter_data|device-limiter' | head -1 || true)"
  if [[ -n "$vol_name" ]]; then
    docker run --rm \
      -v "${vol_name}:/data:ro" \
      -v "$infra_dir:/out" \
      alpine:3.20 \
      sh -c 'tar czf /out/device-limiter-data.tar.gz -C /data .' 2>/dev/null \
      || log_warn "[infra] Device limiter volume export failed"
  elif [[ -n "${DEVICE_LIMITER_CONTAINER:-}" ]]; then
    docker run --rm \
      --volumes-from "$DEVICE_LIMITER_CONTAINER" \
      -v "$infra_dir:/out" \
      alpine:3.20 \
      sh -c 'tar czf /out/device-limiter-data.tar.gz -C /data .' 2>/dev/null \
      || log_warn "[infra] Device limiter volumes-from export failed"
  else
    log_warn "[infra] Device limiter volume not found"
  fi

  log_info "[infra] IP limiter..."
  if [[ -f "$IP_LIMITER_CONFIG" ]]; then
    cp -a "$IP_LIMITER_CONFIG" "$infra_dir/ip-limiter.config.json"
  else
    log_warn "[infra] IP limiter config not found at $IP_LIMITER_CONFIG"
  fi

  log_info "[infra] Nginx repo configs..."
  if [[ -d "$BOT_ROOT/infrastructure/nginx" ]]; then
    tar -cf "$infra_dir/nginx-repo.tar" -C "$BOT_ROOT/infrastructure" nginx
  fi

  log_info "[infra] Nginx live configs..."
  local nginx_tmp
  nginx_tmp="$(mktemp -d)"
  mkdir -p "$nginx_tmp/sites-available" "$nginx_tmp/sites-enabled"
  if [[ -d "$NGINX_LIVE_DIR/sites-available" ]]; then
    find "$NGINX_LIVE_DIR/sites-available" -maxdepth 1 -type f \
      \( -name '*bigadler*' -o -name '*ibaxgames*' -o -name '*noranx*' \) \
      -exec cp -a {} "$nginx_tmp/sites-available/" \; 2>/dev/null || true
  fi
  if [[ -d "$NGINX_LIVE_DIR/sites-enabled" ]]; then
    find "$NGINX_LIVE_DIR/sites-enabled" -maxdepth 1 -type f \
      \( -name '*bigadler*' -o -name '*ibaxgames*' -o -name '*noranx*' \) \
      -exec cp -a {} "$nginx_tmp/sites-enabled/" \; 2>/dev/null || true
  fi
  tar -cf "$infra_dir/nginx-live.tar" -C "$nginx_tmp" sites-available sites-enabled
  rm -rf "$nginx_tmp"

  if [[ "$skip_tls" -eq 0 ]]; then
    log_info "[infra] TLS certificates..."
    backup_tls_certs "$infra_dir/tls-letsencrypt.tar.gz"
  else
    log_info "[infra] Skipping TLS (--skip-tls)"
  fi

  log_info "[infra] Systemd unit..."
  if [[ -f "$BOT_ROOT/infrastructure/systemd/noranx-bot.service" ]]; then
    cp -a "$BOT_ROOT/infrastructure/systemd/noranx-bot.service" "$infra_dir/systemd/noranx-bot.service"
  fi
}
