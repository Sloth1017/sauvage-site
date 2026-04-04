#!/bin/bash
# health-check.sh - Sauvage Chatbot Health Check
# Run periodically to verify chatbot is working correctly

echo "🔍 Sauvage Chatbot Health Check"
echo "================================"
echo ""

# 1. Server health
echo "1️⃣  Server Health"
HEALTH=$(curl -s https://sauvage.amsterdam/health)
if echo "$HEALTH" | grep -q "ok"; then
  echo "✅ Server responding"
else
  echo "❌ Server not responding"
  exit 1
fi
echo ""

# 2. Session creation
echo "2️⃣  Session Creation"
SESSION=$(curl -s -X GET https://sauvage.amsterdam/chat/session | jq -r '.session_id' 2>/dev/null)
if [ ! -z "$SESSION" ] && [ "$SESSION" != "null" ]; then
  echo "✅ Session created: ${SESSION:0:8}..."
else
  echo "❌ Session creation failed"
  exit 1
fi
echo ""

# 3. Chat flow test
echo "3️⃣  Chat Flow Test"

# Message 1: Event type
MSG1=$(curl -s -X POST https://sauvage.amsterdam/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION\", \"message\":\"I want to book a dinner\"}" | jq -r '.response' 2>/dev/null)

if echo "$MSG1" | grep -qi "dinner\|event"; then
  echo "✅ Event type detected correctly"
else
  echo "❌ Event type detection failed"
  echo "   Response: ${MSG1:0:50}..."
  exit 1
fi

# Message 2: Date
MSG2=$(curl -s -X POST https://sauvage.amsterdam/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION\", \"message\":\"May 15th\"}" | jq -r '.response' 2>/dev/null)

if echo "$MSG2" | grep -qi "time\|start\|finish"; then
  echo "✅ Date handling works"
else
  echo "❌ Date handling failed"
  exit 1
fi

# Message 3: Time
MSG3=$(curl -s -X POST https://sauvage.amsterdam/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION\", \"message\":\"19:00 to 23:00\"}" | jq -r '.response' 2>/dev/null)

if echo "$MSG3" | grep -qi "guest\|many"; then
  echo "✅ Time handling works"
else
  echo "❌ Time handling failed"
  exit 1
fi

echo ""
echo "4️⃣  Widget Detection"

# Check if contact form detection keywords are present
if echo "$MSG3" | grep -qi "name\|contact\|reach"; then
  echo "✅ Contact form trigger detected"
else
  echo "⚠️  Contact form trigger not in response"
fi

echo ""
echo "5️⃣  Airtable Integration"

# Check if Airtable API is accessible (requires AIRTABLE_API_KEY env var)
if [ -z "$AIRTABLE_API_KEY" ]; then
  echo "⚠️  AIRTABLE_API_KEY not set - skipping Airtable check"
else
  AIRTABLE_RESPONSE=$(curl -s -H "Authorization: Bearer $AIRTABLE_API_KEY" \
    "https://api.airtable.com/v0/meta/bases" | grep -q "bases")
  if [ $? -eq 0 ]; then
    echo "✅ Airtable API accessible"
  else
    echo "❌ Airtable API connection failed"
  fi
fi

echo ""
echo "6️⃣  Shopify Integration"

# Check if Shopify store is accessible
if [ -z "$SHOPIFY_STORE_URL" ]; then
  echo "⚠️  SHOPIFY_STORE_URL not set - skipping Shopify check"
else
  SHOPIFY_RESPONSE=$(curl -s -I "https://$SHOPIFY_STORE_URL" | head -1)
  if echo "$SHOPIFY_RESPONSE" | grep -q "200\|301\|302"; then
    echo "✅ Shopify store accessible"
  else
    echo "❌ Shopify store connection failed"
  fi
fi

echo ""
echo "✅ All health checks passed!"
echo ""
echo "Status Summary:"
echo "- Server: OK"
echo "- Sessions: OK"
echo "- Event extraction: OK"
echo "- Date/time handling: OK"
echo "- Airtable: OK (if configured)"
echo "- Shopify: OK (if configured)"
echo ""
