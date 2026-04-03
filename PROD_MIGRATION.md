# Production Migration — Environment Variables

## Summary
You've configured all credentials to load from environment variables instead of hardcoded config.py. This requires a one-time setup on the production server.

## ⚠️ You Need to Do This (Requires Sudo)

### Step 1: Deploy Updated Config
```bash
ssh root@31.97.35.5
cd /var/www/sauvage

# Backup old config
cp config.py config.py.backup

# Copy new config from workspace
cp /home/greg/.openclaw/workspace/sauvage/backend/config.py .
chmod 644 config.py
```

### Step 2: Create .env File
```bash
# Create .env with all credentials
# (Use values from your secure credential store)
cat > /var/www/sauvage/.env << 'EOF'
AIRTABLE_API_KEY=pat_YOUR_AIRTABLE_TOKEN_HERE
AIRTABLE_BASE_ID=app_YOUR_BASE_ID_HERE
SHOPIFY_STORE_URL=selection-sauvage-nl.myshopify.com
SHOPIFY_ADMIN_API_TOKEN=shpat_YOUR_SHOPIFY_TOKEN_HERE
SHOPIFY_WEBHOOK_SECRET=YOUR_WEBHOOK_SECRET_HERE
SHOPIFY_API_VERSION=2026-01
BASE_URL=https://booking.selectionsauvage.nl
ANTHROPIC_API_KEY=sk-ant-YOUR_API_KEY_HERE
EOF

# Secure permissions
chmod 600 /var/www/sauvage/.env
chown root:root /var/www/sauvage/.env
```

⚠️ **Replace the placeholders above with your actual credentials from:**
- Airtable: https://airtable.com/create/tokens
- Shopify Admin API token: Shopify Admin → Apps → Develop apps
- Webhook secret: Shopify Admin → Settings → Notifications
- Anthropic: https://console.anthropic.com/

### Step 3: Update Systemd Service
```bash
# Edit the service file
nano /etc/systemd/system/sauvage.service
```

Replace the entire file with:
```ini
[Unit]
Description=Sauvage Chatbot Backend
After=network.target

[Service]
Type=notify
User=root
WorkingDirectory=/var/www/sauvage
EnvironmentFile=/var/www/sauvage/.env
ExecStart=/var/www/sauvage/venv/bin/gunicorn \
    --workers 2 \
    --bind 127.0.0.1:5000 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Save with Ctrl+X, Y, Enter.

### Step 4: Reload & Restart
```bash
systemctl daemon-reload
systemctl restart sauvage
systemctl status sauvage
```

### Step 5: Verify
```bash
# Should return {"status": "ok"}
curl http://localhost:5000/health

# Should return {"session_id": "..."}
curl http://localhost:5000/chat/session

# Should show no warnings about missing environment variables
ps aux | grep gunicorn
```

## What Changed

| File | Before | After |
|------|--------|-------|
| `config.py` | Hardcoded secrets | Reads from environment |
| `.env` | N/A | **New** — stores credentials |
| `.gitignore` | Doesn't exclude `.env` | **Updated** — `.env` never committed |
| Systemd service | Inline env vars | Loads from `EnvironmentFile` |

## Why This Matters

- ✅ **Secrets not in git** — no risk of accidental commits
- ✅ **Easy rotation** — change credentials without redeploying code
- ✅ **Audit trail** — environment variables are logged separately
- ✅ **CI/CD ready** — ready for container deployment (Docker, K8s, etc.)
- ✅ **Follows 12-factor app principles**

## Rollback (If Needed)

If anything breaks:
```bash
# Restore old config
cp /var/www/sauvage/config.py.backup /var/www/sauvage/config.py
systemctl restart sauvage
```

## Next Steps

Once this is deployed:
1. Old `config.py` with secrets can be safely deleted
2. Credentials can be rotated independently
3. Multiple environments (dev/staging/prod) can use different `.env` files
