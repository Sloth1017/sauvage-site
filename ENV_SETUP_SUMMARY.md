# Environment Variables Setup — Summary

## ✅ What's Been Done

### Files Created/Modified

1. **`backend/config.py`** (NEW)
   - Reads all credentials from environment variables
   - Graceful fallbacks for optional variables
   - Validation function warns if required vars are missing
   - Supports `.env` files via `python-dotenv`

2. **`backend/.env.example`** (NEW)
   - Template showing all required variables
   - Safe to commit (no real secrets)
   - Copy this to create your own `.env`

3. **`backend/.env`** (NEW, in `.gitignore`)
   - Actual credentials for local development
   - Never committed to git
   - Format: `KEY=value`, one per line

4. **`.gitignore`** (UPDATED)
   - `.env` added (never commit secrets)
   - `backend/.env` added
   - Already prevents commit of config files

5. **`DEPLOYMENT.md`** (NEW)
   - Complete production deployment guide
   - Options for systemd, Docker, etc.
   - Troubleshooting section

6. **`SECURITY.md`** (NEW)
   - Security checklist
   - How to rotate credentials
   - How to handle exposed secrets

7. **`PROD_MIGRATION.md`** (NEW)
   - Step-by-step production server setup
   - Requires sudo access (must be done by you)
   - Systemd service configuration

## 🎯 What You Need to Do

### Option A: Automated (Recommended)
Request sudo access or ask your sysadmin to run the commands in `PROD_MIGRATION.md`:
- Copy new `config.py` to `/var/www/sauvage/`
- Create `.env` file with credentials
- Update systemd service
- Restart gunicorn

### Option B: Manual
1. SSH to production server
2. Follow steps in `PROD_MIGRATION.md`
3. Verify with health check

## 📋 Checklist

Before going live with environment variables:

- [ ] Review `SECURITY.md` for best practices
- [ ] Run migrations steps from `PROD_MIGRATION.md` (or ask sysadmin)
- [ ] Verify `/health` endpoint returns `{"status": "ok"}`
- [ ] Test chatbot: `/chat/session` → `/chat` with a message
- [ ] Confirm no warnings about missing env vars in systemd logs
- [ ] (Optional) Delete old `config.py.backup` from production server

## 🔒 Credentials Locations

| Credential | Where to Find |
|------------|---------------|
| Airtable API Key | https://airtable.com/create/tokens |
| Airtable Base ID | Your Airtable base URL |
| Shopify Admin Token | Shopify Admin → Apps → Develop apps |
| Shopify Webhook Secret | Shopify Admin → Settings → Notifications |
| Anthropic API Key | https://console.anthropic.com/ |

## 🚀 Local Development

To test locally after migration:

```bash
cd backend

# Copy example to actual
cp .env.example .env

# Edit with your credentials
nano .env

# Install dependencies (if needed)
pip install -r requirements.txt

# Run Flask
python -m dotenv run flask run
```

## 📝 Why This Matters

✅ **Security**: Secrets no longer in code
✅ **Flexibility**: Change credentials without redeploying
✅ **Audit**: Environment variables logged separately
✅ **DevOps**: Ready for CI/CD, Docker, Kubernetes
✅ **Best Practice**: Follows 12-factor app principles

## ⚠️ Common Mistakes to Avoid

❌ Don't commit `.env` (already in `.gitignore`)
❌ Don't hardcode secrets in Python code
❌ Don't share `.env` file in Slack/email
❌ Don't check if credentials are in git history
✅ Do rotate credentials after exposure
✅ Do use strong secrets (random strings for `ADMIN_SECRET`)
✅ Do keep `.env.example` updated with all required keys

## 🆘 Troubleshooting

**"ModuleNotFoundError: No module named 'dotenv'"**
→ Install: `pip install python-dotenv`

**"Warning: Missing environment variables"**
→ Check that all required vars are in `.env` or system environment

**"Permission denied: /var/www/sauvage/.env"**
→ Fix: `sudo chmod 600 /var/www/sauvage/.env`

**Chatbot not responding**
→ Check systemd logs: `sudo journalctl -u sauvage -n 50`

## 📚 References

- [12 Factor App - Config](https://12factor.net/config)
- [Python dotenv docs](https://github.com/theskumar/python-dotenv)
- [Security best practices](https://owasp.org/www-community/attacks/Sensitive_Data_Exposure)
