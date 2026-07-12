#!/usr/bin/env bash
# Legacy wrapper — full stack backup is in stack_backup.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/stack_backup.sh" --bot-only "$@"
