#!/usr/bin/env bash
set -euo pipefail
echo "Rolling back Marzban from /root/restore-safety/marzban-pre ..."
if [[ -d /root/restore-safety/marzban-pre/marzban ]]; then
  cd /opt/marzban && docker compose down || true
  rm -rf /var/lib/marzban
  cp -a /root/restore-safety/marzban-pre/marzban /var/lib/marzban
  cp -a /root/restore-safety/marzban-pre/.env /opt/marzban/.env
  cp -a /root/restore-safety/marzban-pre/docker-compose.yml /opt/marzban/docker-compose.yml
  cd /opt/marzban && docker compose up -d
  echo "Rollback complete — fresh Marzban state restored"
else
  echo "No safety backup found at /root/restore-safety/marzban-pre"
  exit 1
fi
