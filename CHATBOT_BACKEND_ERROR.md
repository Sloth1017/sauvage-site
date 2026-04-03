# Chatbot Backend Issue — SSL Certificate Missing

## Problem

The chatbot widget is showing "please check your internet and try again" error because the API endpoint is not responding.

### Root Cause

**booking.selectionsauvage.nl** has no SSL certificate.

```
Error: cannot load certificate "/etc/letsencrypt/live/booking.selectionsauvage.nl/fullchain.pem"
```

The nginx config at `/etc/nginx/sites-available/sauvage` references certificates that don't exist:

```nginx
ssl_certificate /etc/letsencrypt/live/booking.selectionsauvage.nl/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/booking.selectionsauvage.nl/privkey.pem;
```

## Status

- ✅ Gunicorn backend is running on localhost:5000
- ✅ Nginx is configured to proxy requests
- ❌ SSL certificates are missing → nginx won't start
- ❌ Widget.js can't reach API endpoint (connection timeout)

## Solution (Requires Sudo/Root)

Generate SSL certificate for booking.selectionsauvage.nl:

```bash
sudo certbot certonly --nginx -d booking.selectionsauvage.nl
```

Or use a wildcard certificate:

```bash
sudo certbot certonly --nginx -d selectionsauvage.nl -d *.selectionsauvage.nl
```

Then reload nginx:

```bash
sudo systemctl reload nginx
```

Verify:

```bash
curl https://booking.selectionsauvage.nl/health
# Should return: {"status": "ok"}
```

## Alternative: Use sauvage.amsterdam Certificate

If booking.selectionsauvage.nl isn't critical, you could serve the chatbot API from sauvage.amsterdam instead:

1. Update widget.js:
   ```javascript
   const API = "https://sauvage.amsterdam";  // instead of booking.selectionsauvage.nl
   ```

2. Add endpoint to sauvage.amsterdam nginx config:
   ```nginx
   location /chat/ {
       proxy_pass http://127.0.0.1:5000/chat/;
       # ... other headers
   }
   ```

3. Restart nginx and test

## Next Steps

1. ⏳ Run `sudo certbot certonly --nginx -d booking.selectionsauvage.nl`
2. ⏳ Run `sudo systemctl reload nginx`
3. ⏳ Test: `curl https://booking.selectionsauvage.nl/health`
4. Verify widget works on sauvage.amsterdam

Once this is done, the chatbot will connect properly!
