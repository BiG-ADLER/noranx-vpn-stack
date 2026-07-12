#!/usr/bin/env bash
# Deploy pudge.noranx.ir nginx on Germany VPS (178.83.46.103)
set -euo pipefail

DE_HOST="${DE_HOST:-root@178.83.46.103}"
CONF_SRC="${CONF_SRC:-/root/noranx_vpn_bot/infrastructure/nginx/pudge.noranx.ir.conf}"
DOMAIN="pudge.noranx.ir"
WEBROOT="/var/www/${DOMAIN}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20 -i /root/.ssh/id_ed25519)

echo "=== Deploy ${DOMAIN} to ${DE_HOST} ==="

ssh "${SSH_OPTS[@]}" "${DE_HOST}" "mkdir -p ${WEBROOT} /root/backups"

BOOTSTRAP=$(mktemp)
head -72 "$CONF_SRC" > "$BOOTSTRAP"
scp "${SSH_OPTS[@]}" "$BOOTSTRAP" "${DE_HOST}:/etc/nginx/sites-available/${DOMAIN}.conf"
ssh "${SSH_OPTS[@]}" "${DE_HOST}" \
  "ln -sf /etc/nginx/sites-available/${DOMAIN}.conf /etc/nginx/sites-enabled/${DOMAIN}.conf && nginx -t && systemctl reload nginx"

ssh "${SSH_OPTS[@]}" "${DE_HOST}" \
  "certbot certonly --webroot -w ${WEBROOT} -d ${DOMAIN} --non-interactive --agree-tos --register-unsafely-without-email"

scp "${SSH_OPTS[@]}" "$CONF_SRC" "${DE_HOST}:/etc/nginx/sites-available/${DOMAIN}.conf"
ssh "${SSH_OPTS[@]}" "${DE_HOST}" "nginx -t && systemctl reload nginx"
rm -f "$BOOTSTRAP"

for path in /ws /trojan /vmess; do
  echo "=== origin ${path} ==="
  ssh "${SSH_OPTS[@]}" "${DE_HOST}" \
    "curl -si --max-time 8 -H 'Host: ${DOMAIN}' -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' http://127.0.0.1${path} | head -2"
done

echo "=== Done ${DOMAIN} ==="
