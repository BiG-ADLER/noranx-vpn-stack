#!/bin/bash
# verify.sh - Local verification script for Marzban-Device-Limit

BASE_URL="http://localhost:3000"
USERNAME="user1"
# "user1" in base64
TOKEN="dXNlcjE="

echo "🔍 Starting Verification..."

echo -n "1. Checking empty devices list... "
RESP=$(curl -s "$BASE_URL/api/devices?username=$USERNAME")
if [[ "$RESP" == "null" ]] || [[ "$RESP" == "[]" ]]; then
    echo "✅ OK"
else
    echo "❌ Failed (Expected [], got $RESP)"
fi

echo "2. Sending Proxy Request (Simulating Client)... "
# We expect 404 or 502 from upstream (real Marzban) because token is fake, 
# but our Middleware should process it anyway.
curl -s -o /dev/null -H "User-Agent: v2rayNG/1.8.5" -H "X-HWID: test-hwid-1" "$BASE_URL/sub/$TOKEN"
echo "✅ Sent"

echo -n "3. Checking devices list (Expect 1 device)... "
RESP=$(curl -s "$BASE_URL/api/devices?username=$USERNAME")
if [[ "$RESP" == *"test-hwid-1"* ]]; then
    echo "✅ OK (Found test-hwid-1)"
else
    echo "❌ Failed (Device not found in $RESP)"
fi

echo -n "4. Testing Limit (Set to 0 to block)... "
# Set limit to 0
curl -s -X PUT -d '{"username":"user1", "device_limit": 0, "hwid_enabled": true}' "$BASE_URL/api/limit" > /dev/null

# Request should now be forbidden (403)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "User-Agent: v2rayNG/1.8.5" -H "X-HWID: test-hwid-2" "$BASE_URL/sub/$TOKEN")

if [[ "$HTTP_CODE" == "403" ]]; then
    echo "✅ OK (Got 403 Forbidden)"
else
    echo "❌ Failed (Expected 403, got $HTTP_CODE)"
fi

echo "📝 Verification Complete."
