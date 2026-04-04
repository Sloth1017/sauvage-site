# Automated Thank You Email Setup

When a customer's deposit is paid, the chatbot automatically sends them a branded thank you email with booking details and emergency contacts.

## Setup Instructions

### Option 1: Gmail (Easiest) ✅

1. **Create a Gmail account** for Sauvage (or use existing):
   - Email: `noreply@sauvage.amsterdam` (or any Gmail address)
   - Password: (use App Password, not your regular Gmail password)

2. **Generate Gmail App Password:**
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and "Windows Computer" (or your device)
   - Google generates a 16-character password
   - Copy it

3. **Set environment variables** on production server:
   ```bash
   export SMTP_SERVER="smtp.gmail.com"
   export SMTP_PORT="587"
   export SMTP_USER="your-gmail@gmail.com"
   export SMTP_PASSWORD="your-16-char-app-password"
   export FROM_EMAIL="noreply@sauvage.amsterdam"
   ```

4. **Add to systemd service** (permanent):
   ```bash
   sudo nano /etc/systemd/system/sauvage.service
   ```
   
   Add under `[Service]` section:
   ```ini
   Environment="SMTP_SERVER=smtp.gmail.com"
   Environment="SMTP_PORT=587"
   Environment="SMTP_USER=your-gmail@gmail.com"
   Environment="SMTP_PASSWORD=your-16-char-app-password"
   Environment="FROM_EMAIL=noreply@sauvage.amsterdam"
   ```

5. **Restart service**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart sauvage
   ```

### Option 2: SendGrid (More Reliable)

1. **Create SendGrid account:** https://sendgrid.com
2. **Generate API key** in dashboard
3. **Set environment variables:**
   ```bash
   export SMTP_SERVER="smtp.sendgrid.net"
   export SMTP_PORT="587"
   export SMTP_USER="apikey"
   export SMTP_PASSWORD="sg_xxxxxxxxxxxx"
   export FROM_EMAIL="noreply@sauvage.amsterdam"
   ```

### Option 3: Your Own Mail Server

If you have your own mail server, update the SMTP settings accordingly.

---

## Email Template Customization

The email includes:
- ✅ Client name & booking details
- ✅ Event type, date, time, guests
- ✅ Rooms booked
- ✅ Google Calendar link (when available)
- ✅ Link to Terms & Conditions
- ✅ Emergency contact phone + email
- ✅ Sauvage branding

To customize the phone number and emergency email, edit `/home/greg/.openclaw/workspace/sauvage/backend/chat_backend.py` and find the `send_confirmation_email()` function. Update:

```python
<strong>Phone:</strong> +31 (0)6 12345678<br>
<strong>Email:</strong> <a href="mailto:contact@selectionsauvage.nl">contact@selectionsauvage.nl</a>
```

Replace with your actual details.

---

## Testing

1. Make sure environment variables are set
2. Do a test booking through the chatbot
3. Complete payment in Shopify
4. Wait 30 seconds
5. Check your email inbox for the thank you email

If you don't receive it:
- Check server logs: `sudo journalctl -u sauvage -n 50`
- Verify SMTP credentials are correct
- Check spam folder (Gmail sometimes routes to spam)

---

## Troubleshooting

### "SMTP credentials not configured"
- Ensure all 4 environment variables are set
- Run `echo $SMTP_USER` to verify

### "Connection refused"
- Check SMTP_PORT (Gmail uses 587, not 25)
- Verify firewall allows outbound port 587

### "Invalid credentials"
- For Gmail: Make sure you used App Password, not regular password
- For SendGrid: Verify API key starts with `sg_`

### Email in spam folder
- Add `noreply@sauvage.amsterdam` to contacts
- Gmail's default filters sometimes mark automated emails as spam

---

**Last Updated:** April 4, 2026
