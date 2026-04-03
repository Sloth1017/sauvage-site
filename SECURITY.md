# Security Hardening — Sauvage Chatbot

## ✅ Changes Made

### 1. Credentials Removed from Code
- **Before**: Secrets hardcoded in `backend/config.py`
- **After**: All credentials loaded from environment variables via `.env` file

### 2. Files Added
- `backend/.env.example` — template showing all required variables (safe to commit)
- `DEPLOYMENT.md` — complete guide for production setup
- `.env` files added to `.gitignore` (never committed)

### 3. Config.py Rewritten
- Now reads from `os.getenv()` with fallbacks
- Includes validation function to warn about missing variables
- Supports local `.env` files via `python-dotenv`

## 🔐 What's Protected

| Credential | Storage | Risk Level |
|-----------|---------|-----------|
| Airtable API Key | `.env` (not in git) | 🔴 High |
| Shopify Admin Token | `.env` (not in git) | 🔴 High |
| Shopify Webhook Secret | `.env` (not in git) | 🔴 High |
| Anthropic API Key | `.env` (not in git) | 🔴 High |
| Admin Secret | Environment var | 🟡 Medium |

## 📋 Deployment Checklist

- [ ] Create `.env` file at `/var/www/sauvage/.env`
- [ ] Set permissions: `sudo chmod 600 /var/www/sauvage/.env`
- [ ] Update systemd service to load from `EnvironmentFile=/var/www/sauvage/.env`
- [ ] Restart gunicorn: `sudo systemctl restart sauvage`
- [ ] Verify config loads: `python backend/config.py` (should not warn)
- [ ] Test API: `curl http://localhost:5000/health`

## 🔑 How to Generate New Credentials

### Airtable
1. Go to https://airtable.com/create/tokens
2. Create new token with scopes:
   - `data.records:read`
   - `data.records:write`
   - `schema.bases:read`
   - `schema.bases:write`
3. Copy token → paste in `.env`

### Shopify
1. Admin → Settings → Apps and sales channels
2. Develop apps → Create app → "Sauvage Chatbot"
3. Configuration → Admin API scopes, enable:
   - `write_draft_orders`
   - `read_draft_orders`
   - `read_orders`
4. Install → copy Admin API access token
5. For webhook secret: Settings → Notifications → Webhooks → copy signing secret

### Anthropic
1. Go to https://console.anthropic.com/
2. Generate new API key
3. Copy → paste in `.env`

## ⚠️ Never Do This

```bash
# ❌ WRONG — commits secrets to git
git add backend/config.py
git push

# ❌ WRONG — hardcodes credentials
AIRTABLE_API_KEY = "pat_xxx..." in code

# ❌ WRONG — commits .env to git
git add backend/.env
```

## ✅ Always Do This

```bash
# ✅ RIGHT — .env is ignored
echo "backend/.env" >> .gitignore

# ✅ RIGHT — use environment variables
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")

# ✅ RIGHT — .env.example shows what's needed (no real values)
# backend/.env.example lists required vars with dummy values
```

## 🚨 If a Secret is Exposed

1. **Immediately revoke** the exposed credential in its service (Airtable, Shopify, Anthropic)
2. **Generate new credential** with same permissions
3. **Update `.env` file** with new value
4. **Restart gunicorn**: `sudo systemctl restart sauvage`
5. Never commit the old secret to git again

## 📚 References

- [Anthropic API Docs](https://docs.anthropic.com/claude/reference/authentication)
- [Airtable API Tokens](https://airtable.com/create/tokens)
- [Shopify Admin API](https://shopify.dev/docs/api/admin-rest)
- [12 Factor App - Config](https://12factor.net/config)
