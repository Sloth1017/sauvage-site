# Sauvage Amsterdam — Deployment Status ✅

**Date:** Friday, April 3, 2026
**Status:** 🟢 **LIVE AND OPERATIONAL**

---

## 📊 System Status

| Component | Status | URL |
|-----------|--------|-----|
| Website | ✅ Live | https://sauvage.amsterdam |
| Chatbot API | ✅ Live | https://sauvage.amsterdam/chat |
| Airtable Integration | ✅ Ready | app4rCwUqnJ5A28YH |
| Shopify Integration | ✅ Ready | selection-sauvage-nl.myshopify.com |
| SSL Certificates | ✅ Valid | Let's Encrypt |

---

## 🎨 Website

### Current Features
- ✅ Responsive design (mobile, tablet, desktop)
- ✅ Hero section with "Book Event" CTA
- ✅ The Space section (multi-purpose venue)
- ✅ Offerings section (Café, Exhibition, Natural Wines)
- ✅ Events section (Luma calendar)
- ✅ DAO & Web3 section
- ✅ Exhibition (Kinship)
- ✅ Contact form with location

### Recent Changes (Today)
- Removed wine section
- Redesigned Offerings with article-style layout
- Updated typography to match design system
- Added quick-action links (Ikinari, Sauvage Cafe, Fento)
- Changed hero button to "Book Event" → Opens chatbot

---

## 💬 Chatbot Booking System

### API Endpoints
```
GET  /chat/session                    — Create new session
POST /chat                            — Send message, get response
GET  /chat/payment-status/<sid>      — Check booking status
```

### Integration Workflow
1. User starts chat → Claude assistant takes over
2. Chatbot extracts booking details (date, email, event type, etc.)
3. Details synced to Airtable in real-time
4. When booking complete → Shopify creates draft order
5. Checkout link injected into chat
6. Payment confirmed → Airtable updated
7. Bot detects confirmation → Booking locked in

### Booking Flow
- Step 1: Event type selection (Birthday, Corporate, Pop-up, Dinner, Art Gallery, Wine Tasting, Workshop, Other)
- Step 2: Date/time details
- Step 3: Contact information (name, email, phone)
- Step 4: Space & add-ons selection (Entrance, Gallery, Kitchen, Cave)
- Step 5: Quote + payment deposit

---

## 🔐 Security

### Credentials Management
- ✅ All secrets in environment variables (not in code)
- ✅ `.env` file secured (600 permissions)
- ✅ `.gitignore` prevents accidental commits
- ✅ Configuration documented in DEPLOYMENT.md

### Recommended Actions
1. Rotate Shopify Admin Token regularly (quarterly)
2. Rotate Airtable API key (quarterly)
3. Monitor Anthropic API usage for abuse
4. Keep SSL certificates renewed (auto via certbot)

---

## 📋 Deployment Checklist

### ✅ Completed
- [x] Website deployed to sauvage.amsterdam
- [x] Chatbot backend running (gunicorn)
- [x] Nginx reverse proxy configured
- [x] SSL certificates installed
- [x] Widget.js serving from workspace (live updates)
- [x] API endpoints responding
- [x] Airtable integration configured
- [x] Shopify integration configured
- [x] Environment variables setup documented

### ⏳ Pending (Optional)
- [ ] Run PROD_MIGRATION.md for env vars (already in place, just needs review)
- [ ] Install Google Calendar libs (for better availability checking)
- [ ] Set up email notifications for bookings
- [ ] Configure Sentry/error tracking
- [ ] Set up analytics (GA4, Hotjar, etc.)

---

## 🚀 Testing

### Manual Tests (Passed ✅)
```bash
# Health check
curl https://sauvage.amsterdam/health
# Response: {"status": "ok"}

# Create chat session
curl https://sauvage.amsterdam/chat/session
# Response: {"session_id": "..."}

# Send message
curl -X POST https://sauvage.amsterdam/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test", "message":"I want to book a dinner"}'
# Response: Bot response + greeting
```

### Widget Testing
1. Visit https://sauvage.amsterdam
2. Click chatbot bubble (bottom right)
3. Select event type → confirm chatbot responds
4. Continue conversation → verify all steps work

---

## 📞 Support

### Common Issues

**Chatbot not loading?**
- Clear browser cache
- Check browser console for CORS errors
- Verify sauvage.amsterdam is responsive

**Connection error in chatbot?**
- Check nginx logs: `sudo journalctl -u nginx -n 50`
- Verify backend: `curl https://sauvage.amsterdam/health`
- Restart service: `sudo systemctl restart sauvage`

**Airtable not syncing?**
- Verify API key is set in environment variables
- Check that AIRTABLE_BASE_ID matches your base
- Review app.py logs for sync errors

---

## 📞 Contacts & Resources

- **Airtable Base:** https://airtable.com/app4rCwUqnJ5A28YH
- **Selection Sauvage:** https://www.selectionsauvage.nl
- **Fento (Cafe):** https://www.thefento.com
- **GitHub Repo:** https://github.com/Sloth1017/sauvage-site

---

## 📚 Documentation

- `DEPLOYMENT.md` — Full deployment guide
- `SECURITY.md` — Security best practices
- `ENV_SETUP_SUMMARY.md` — Environment variables checklist
- `CHATBOT_BACKEND_ERROR.md` — SSL certificate troubleshooting
- `PROD_MIGRATION.md` — Production server migration guide

---

**Last Updated:** Friday, April 3, 2026, 06:56 UTC  
**Deployed By:** Jobsearcho (automated deployment)  
**Status:** 🟢 Fully Operational
