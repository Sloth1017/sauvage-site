# Deployment Guide — Sauvage Chatbot

## Environment Variables

All credentials are now loaded from environment variables (not committed to git).

### Setup

1. **Create `.env` file** in `backend/` directory:
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env and fill in your credentials
   ```

2. **Required variables**:
   - `AIRTABLE_API_KEY` — from https://airtable.com/create/tokens
   - `AIRTABLE_BASE_ID` — your Airtable base ID
   - `SHOPIFY_STORE_URL` — e.g., `selection-sauvage-nl.myshopify.com`
   - `SHOPIFY_ADMIN_API_TOKEN` — from Shopify Admin
   - `SHOPIFY_WEBHOOK_SECRET` — from Shopify webhooks
   - `ANTHROPIC_API_KEY` — from https://console.anthropic.com/

### Production Deployment

#### Option 1: Systemd Service (Recommended)

1. **Create `.env` file at `/var/www/sauvage/.env`** with all credentials

2. **Update systemd service**:
   ```bash
   sudo systemctl stop sauvage
   sudo nano /etc/systemd/system/sauvage.service
   ```
   
   Replace with:
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

3. **Reload and restart**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start sauvage
   sudo systemctl status sauvage
   ```

#### Option 2: Docker (Future)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend .
ENV PYTHONUNBUFFERED=1
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
```

Run with:
```bash
docker run --env-file .env -p 5000:5000 sauvage-chatbot
```

## Testing

### Local Development

1. **Install dependencies**:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install python-dotenv
   ```

2. **Create `.env` with credentials**

3. **Run Flask**:
   ```bash
   python -m dotenv run flask run
   ```

### Test the API

```bash
# Create session
curl -X GET http://localhost:5000/chat/session

# Send message
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"YOUR_SESSION_ID", "message":"I want to book an event"}'

# Check payment status
curl -X GET http://localhost:5000/chat/payment-status/YOUR_SESSION_ID
```

## Troubleshooting

### Missing environment variables
If you see warnings about missing env vars, check:
1. `.env` file exists and is readable
2. All required variables are set
3. Run `python backend/config.py` to validate

### Credentials not loading
- Systemd service: Confirm `EnvironmentFile=/var/www/sauvage/.env` in service file
- Flask app: Ensure `dotenv` is installed (`pip install python-dotenv`)

### Permission denied on .env
```bash
sudo chown root:root /var/www/sauvage/.env
sudo chmod 600 /var/www/sauvage/.env
```

## Security Checklist

- [ ] `.env` is in `.gitignore` (never commit)
- [ ] `.env` file has 600 permissions (read-only by service user)
- [ ] Credentials rotated regularly (especially Shopify tokens)
- [ ] ADMIN_SECRET is a strong random string
- [ ] HTTPS enforced for all booking URLs
