#!/usr/bin/env bash
# Restore limiters, nginx, TLS, systemd.
restore_infrastructure() {
  local staging="$1"
  local dry_run="${2:-0}"
  local skip_tls="${3:-0}"
  local infra="$staging/infrastructure"

  if [[ ! -d "$infra" ]]; then
    log_warn "[infra] No infrastructure backup — skip"
    return 0
  fi

  if [[ "$dry_run" -eq 1 ]]; then
    log_info "[infra] Dry-run: would restore infrastructure"
    return 0
  fi

  if [[ -f "$infra/device-limiter.env" ]]; then
    log_info "[infra] Device limiter .env (archived — not auto-started)..."
    mkdir -p "$DEVICE_LIMITER_DIR"
    cp -a "$infra/device-limiter.env" "$DEVICE_LIMITER_DIR/.env"
  fi

  if [[ -f "$infra/device-limiter-data.tar.gz" ]]; then
    log_info "[infra] Device limiter volume (archived — not auto-started)..."
    local vol_name
    vol_name="$(docker volume ls --format '{{.Name}}' | grep -E 'device_limiter_data|device-limiter' | head -1 || true)"
    if [[ -z "$vol_name" ]]; then
      (cd "$DEVICE_LIMITER_DIR" && docker compose up -d --no-start 2>/dev/null || true)
      vol_name="$(docker volume ls --format '{{.Name}}' | grep -E 'device_limiter_data|device-limiter' | head -1 || true)"
    fi
    if [[ -n "$vol_name" ]]; then
      docker run --rm \
        -v "${vol_name}:/data" \
        -v "$infra:/in" \
        alpine:3.20 \
        sh -c 'rm -rf /data/* /data/.[!.]* 2>/dev/null; tar xzf /in/device-limiter-data.tar.gz -C /data'
    else
      log_warn "[infra] Could not locate device limiter volume"
    fi
  fi

  if [[ "${RESTORE_DEVICE_LIMITER:-0}" == "1" && -d "$DEVICE_LIMITER_DIR" ]]; then
    log_info "[infra] Starting device limiter (RESTORE_DEVICE_LIMITER=1)..."
    (cd "$DEVICE_LIMITER_DIR" && docker compose up -d --build) || log_warn "[infra] device limiter start failed"
  else
    log_info "[infra] Skipping device limiter start (retired; set RESTORE_DEVICE_LIMITER=1 to restore)"
  fi

  if [[ -f "$infra/ip-limiter.config.json" ]]; then
    log_info "[infra] IP limiter config..."
    mkdir -p "$(dirname "$IP_LIMITER_CONFIG")"
    cp -a "$infra/ip-limiter.config.json" "$IP_LIMITER_CONFIG"
    if [[ -n "${IP_LIMITER_CONTAINER:-}" ]]; then
      docker restart "$IP_LIMITER_CONTAINER" >/dev/null 2>&1 || true
    fi
  fi

  if [[ -f "$infra/nginx-live.tar" ]]; then
    log_info "[infra] Nginx live configs..."
    mkdir -p "$NGINX_LIVE_DIR/sites-available" "$NGINX_LIVE_DIR/sites-enabled"
    tar -xf "$infra/nginx-live.tar" -C /tmp
    cp -a /tmp/sites-available/* "$NGINX_LIVE_DIR/sites-available/" 2>/dev/null || true
    for f in "$NGINX_LIVE_DIR/sites-available/"*; do
      [[ -f "$f" ]] || continue
      ln -sf "$f" "$NGINX_LIVE_DIR/sites-enabled/$(basename "$f")"
    done
  elif [[ -f "$infra/nginx-repo.tar" ]]; then
    log_info "[infra] Nginx repo configs (no live backup)..."
    tar -xf "$infra/nginx-repo.tar" -C /tmp
    cp -a /tmp/nginx/*.conf "$NGINX_LIVE_DIR/sites-available/" 2>/dev/null || true
    for f in "$NGINX_LIVE_DIR/sites-available/"*bigadler* "$NGINX_LIVE_DIR/sites-available/"*ibaxgames*; do
      [[ -f "$f" ]] || continue
      ln -sf "$f" "$NGINX_LIVE_DIR/sites-enabled/$(basename "$f")"
    done
  fi

  if command -v nginx >/dev/null 2>&1; then
    nginx -t && systemctl reload nginx || log_warn "[infra] nginx reload failed"
  fi

  if [[ "$skip_tls" -eq 0 && -f "$infra/tls-letsencrypt.tar.gz" ]]; then
    log_info "[infra] TLS certificates..."
    restore_tls_certs "$infra/tls-letsencrypt.tar.gz"
  fi

  if [[ -f "$infra/systemd/noranx-bot.service" ]]; then
    log_info "[infra] Systemd unit..."
    cp -a "$infra/systemd/noranx-bot.service" /etc/systemd/system/noranx-bot.service
    systemctl daemon-reload
    systemctl enable noranx-bot.service >/dev/null 2>&1 || true
  fi
}
