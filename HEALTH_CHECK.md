# Sauvage Chatbot Health Check Guide

## Quick Status Check

Run this script periodically to verify the chatbot is working correctly:

```bash
#!/bin/bash
# health-check.sh - Run on production server or locally

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
echo "✅ All health checks passed!"
echo ""
echo "Status Summary:"
echo "- Server: OK"
echo "- Sessions: OK"
echo "- Event extraction: OK"
echo "- Date/time handling: OK"
echo ""
```

## Automated Health Check (Cron)

To run this daily at 9:00 AM UTC:

```bash
# 1. Save the script
nano /home/greg/.openclaw/workspace/sauvage/health-check.sh
# (paste the script above)

# 2. Make it executable
chmod +x /home/greg/.openclaw/workspace/sauvage/health-check.sh

# 3. Add to crontab
crontab -e

# Add this line:
0 9 * * * /home/greg/.openclaw/workspace/sauvage/health-check.sh >> /var/log/sauvage-health.log 2>&1
```

## Manual Testing Checklist

Use this when you want to manually test the chatbot:

### 1. Server Check
```bash
curl -s https://sauvage.amsterdam/health | jq .
# Should return: {"status": "ok"}
```

### 2. Session Creation
```bash
curl -s https://sauvage.amsterdam/chat/session | jq .
# Should return a session_id
```

### 3. Full Booking Flow (Step-by-Step)

```bash
SID="YOUR_SESSION_ID_HERE"

# Step 1: Event type
curl -s -X POST https://sauvage.amsterdam/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\", \"message\":\"I want to book a dinner\"}" | jq '.response'

# Step 2: Date
curl -s -X POST https://sauvage.amsterdam/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\", \"message\":\"May 15th\"}" | jq '.response'

# Step 3: Time
curl -s -X POST https://sauvage.amsterdam/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\", \"message\":\"19:00 to 23:00\"}" | jq '.response'

# Step 4: Guest count
curl -s -X POST https://sauvage.amsterdam/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\", \"message\":\"30 guests\"}" | jq '.response'

# Step 5: Contact info
curl -s -X POST https://sauvage.amsterdam/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\", \"message\":\"Greg, greg@sauvage.nl, +31612345678\"}" | jq '.response'
```

## What to Look For

### ✅ Good Signs
- Server returns 200 with `{"status": "ok"}`
- Session IDs are created correctly
- Bot responds to each message without looping
- Bot asks for the next piece of info (doesn't re-ask what's been answered)
- Bot mentions "calendar", "contact", or "form" when appropriate
- No error messages in responses
- Airtable API responds (requires AIRTABLE_API_KEY)
- Shopify store is accessible (requires SHOPIFY_STORE_URL)

### ⚠️ Warning Signs
- Server returns 500 or timeout
- Session creation fails
- Bot repeats questions already answered (looping)
- Bot doesn't advance the booking flow
- Widget-related keywords missing from responses
- Airtable/Shopify integration errors in logs

## Logs

Check server logs if issues occur:

```bash
# Gunicorn logs (Flask app)
sudo journalctl -u sauvage -n 50 -f

# Nginx logs (reverse proxy)
sudo tail -f /var/log/nginx/error.log

# Application logs (if running)
sudo tail -f /var/log/sauvage-health.log
```

## Sync Production Files

If you detect issues, sync the latest code:

```bash
# Copy latest files from workspace to production
cp /home/greg/.openclaw/workspace/sauvage/widget.js /var/www/sauvage/widget.js
cp /home/greg/.openclaw/workspace/sauvage/backend/chat_backend.py /var/www/sauvage/chat_backend.py
cp /home/greg/.openclaw/workspace/sauvage/backend/chatbot-prompt-v2.md /var/www/sauvage/chatbot-prompt-v2.md

# Restart the service
sudo systemctl restart sauvage

# Verify
curl -s https://sauvage.amsterdam/health | jq .
```

## Monthly Maintenance

1. **First Monday of each month:**
   - Run full health check
   - Review logs for errors
   - Test full booking flow end-to-end
   - Update Airtable credentials if needed
   - Check Shopify integration

2. **Quarterly (every 3 months):**
   - Rotate API keys
   - Review chatbot prompt effectiveness
   - Check calendar sync status
   - Update documentation

3. **When Issues Arise:**
   - Run health check immediately
   - Check logs
   - Sync production files if needed
   - Restart service
   - Re-test

---

**Last Updated:** April 4, 2026
