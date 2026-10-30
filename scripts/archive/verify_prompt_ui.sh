#!/bin/bash
# Verification script to test prompt UI updates

echo "1. Setting test prompt via API..."
RESPONSE=$(curl -s -X PUT http://127.0.0.1:8001/api/workflow/config/prompts \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"CmdlineExtract","prompt":"{\"role\":\"VERIFIED_SYSTEM_123\",\"user_template\":\"VERIFIED_USER_456\"}","instructions":null,"change_description":"Verification test"}')

echo "Response: $RESPONSE"
sleep 2

echo ""
echo "2. Verifying API returns correct data..."
API_DATA=$(curl -s http://127.0.0.1:8001/api/workflow/config/prompts)
SYSTEM=$(echo "$API_DATA" | python3 -c "import sys, json; data = json.load(sys.stdin); cmdline = data.get('prompts', {}).get('CmdlineExtract', {}); prompt = cmdline.get('prompt', ''); import json as j; parsed = j.loads(prompt) if prompt else {}; print(parsed.get('role', ''))")
USER=$(echo "$API_DATA" | python3 -c "import sys, json; data = json.load(sys.stdin); cmdline = data.get('prompts', {}).get('CmdlineExtract', {}); prompt = cmdline.get('prompt', ''); import json as j; parsed = j.loads(prompt) if prompt else {}; print(parsed.get('user_template', ''))")

echo "API System: $SYSTEM"
echo "API User: $USER"

if [ "$SYSTEM" = "VERIFIED_SYSTEM_123" ] && [ "$USER" = "VERIFIED_USER_456" ]; then
    echo "✅ API verification PASSED"
else
    echo "❌ API verification FAILED"
    exit 1
fi

echo ""
echo "3. UI verification requires browser - check console logs for:"
echo "   - 🔄 Loading agent prompts from API..."
echo "   - 📝 CmdlineExtract System (role): VERIFIED_SYSTEM_123"
echo "   - 📝 CmdlineExtract User (user_template): VERIFIED_USER_456"
echo "   - ✅ VERIFIED: CmdlineExtract display matches data"
echo ""
echo "If verification shows mismatch, check console for details."

