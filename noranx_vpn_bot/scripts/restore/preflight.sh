#!/usr/bin/env bash
# Preflight checks for stack restore.
restore_preflight() {
  local archive="$1"
  local extract_root="$2"

  require_root
  require_commands tar sha256sum python3 docker

  if [[ ! -f "$archive" ]]; then
    log_err "Archive not found: $archive"
    return 1
  fi

  log_info "[preflight] Extracting archive to $extract_root..."
  rm -rf "$extract_root"
  mkdir -p "$extract_root"
  tar -xzf "$archive" -C "$extract_root"

  STAGING="$(find "$extract_root" -maxdepth 1 -type d -name 'staging-*' | head -1)"
  if [[ -z "$STAGING" ]]; then
    log_err "No staging-* directory inside archive"
    return 1
  fi

  if [[ ! -f "$STAGING/MANIFEST.json" ]]; then
    log_err "MANIFEST.json missing"
    return 1
  fi

  log_info "[preflight] Verifying checksums..."
  verify_checksums "$STAGING"

  local archive_size avail_kb need_kb
  archive_size="$(stat -c%s "$archive" 2>/dev/null || stat -f%z "$archive")"
  avail_kb="$(df -k "$BOT_ROOT" | awk 'NR==2 {print $4}')"
  need_kb="$((archive_size / 1024 * 2))"
  if [[ "$avail_kb" -lt "$need_kb" ]]; then
    log_warn "[preflight] Low disk space: ${avail_kb}KB free, recommend >= ${need_kb}KB"
  fi

  export RESTORE_STAGING="$STAGING"
  log_info "[preflight] OK — staging=$STAGING"
}
