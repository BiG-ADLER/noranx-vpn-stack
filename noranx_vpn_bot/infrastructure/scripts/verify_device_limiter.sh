#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${1:?usage: verify_device_limiter.sh BASE_URL TOKEN}"
TOKEN="${2:?}"
for i in 1 2 3 4; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "X-HWID: test_device_$i" "${BASE_URL%/}/sub/${TOKEN}")
  echo "HWID test_device_$i -> HTTP $code"
done
