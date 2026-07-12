#!/usr/bin/env bash
# Phase 2: verify/update Cloudflare A records to VPS IP
set -euo pipefail

TARGET_IP="${TARGET_IP:-5.75.201.19}"
RECORDS=(
  "sub.ibaxgames.ir:ibaxgames.ir:sub"
  "panel.bigadler.xyz:bigadler.xyz:panel"
  "de.bigadler.xyz:bigadler.xyz:de"
  "bot.bigadler.xyz:bigadler.xyz:bot"
)

fail=0
echo "=== DNS verify (target $TARGET_IP) ==="
for entry in "${RECORDS[@]}"; do
  host="${entry%%:*}"
  ip=$(dig +short A "$host" @1.1.1.1 | head -1)
  if [[ "$ip" == "$TARGET_IP" ]]; then
    echo "OK: $host -> $ip"
  else
    echo "FAIL: $host -> ${ip:-NONE} (expected $TARGET_IP)"
    fail=1
  fi
done

if [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  echo ""
  echo "=== Cloudflare API update (DNS only / proxied=false) ==="
  CF_AUTH=(-H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json")
  for entry in "${RECORDS[@]}"; do
    host="${entry%%:*}"
    rest="${entry#*:}"
    zone="${rest%%:*}"
    name="${rest##*:}"
    zid=$(curl -fsS "${CF_AUTH[@]}" "https://api.cloudflare.com/client/v4/zones?name=$zone" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result'][0]['id'] if d.get('result') else '')")
    [[ -n "$zid" ]] || { echo "WARN: zone $zone not found"; continue; }
    recs=$(curl -fsS "${CF_AUTH[@]}" "https://api.cloudflare.com/client/v4/zones/$zid/dns_records?type=A&name=$host")
    rid=$(echo "$recs" | python3 -c "import sys,json; r=json.load(sys.stdin)['result']; print(r[0]['id'] if r else '')")
    body=$(python3 -c "import json; print(json.dumps({'type':'A','name':'$name','content':'$TARGET_IP','ttl':120,'proxied':False}))")
    if [[ -n "$rid" ]]; then
      curl -fsS -X PUT "${CF_AUTH[@]}" -d "$body" "https://api.cloudflare.com/client/v4/zones/$zid/dns_records/$rid" >/dev/null
      echo "UPDATED: $host"
    else
      curl -fsS -X POST "${CF_AUTH[@]}" -d "$body" "https://api.cloudflare.com/client/v4/zones/$zid/dns_records" >/dev/null
      echo "CREATED: $host"
    fi
  done
  sleep 3
else
  echo "SKIP: CLOUDFLARE_API_TOKEN not set (DNS verify only)"
fi

exit $fail
