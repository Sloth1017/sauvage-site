# Google Analytics Setup - Sauvage

## Status: ✅ Active

Google Analytics is now integrated with your Sauvage website and chatbot. Measurement ID: `G-P99Q9D5EJ4`

---

## Tracked Events

### 1. **Chatbot Opened** 📱
- **Event Name:** `chatbot_opened`
- **When:** User clicks the floating chat bubble
- **Category:** booking
- **Use:** Understand chatbot engagement rate

### 2. **Booking Session Started** 🎯
- **Event Name:** `booking_session_started`
- **When:** User initiates a new booking conversation
- **Data:** Session ID
- **Use:** Track funnel entry point

### 3. **Payment Completed** 💳
- **Event Name:** `booking_payment_completed`
- **When:** User pays deposit via Shopify
- **Category:** booking
- **Value:** 1 (conversion)
- **Currency:** EUR
- **Use:** **KEY CONVERSION METRIC** - Track successful bookings

---

## How to View Analytics

### 1. **Real-Time Dashboard**
1. Go to https://analytics.google.com
2. Select your Sauvage property
3. Click **Reports** (left sidebar)
4. Click **Real-Time**
5. See live visitors, events, and page views

### 2. **Conversion Tracking**
1. Go to **Reports** → **Engagement** → **Events**
2. Look for:
   - `chatbot_opened` - browsing interest
   - `booking_session_started` - serious inquiries
   - `booking_payment_completed` - confirmed bookings (your main KPI)

### 3. **User Funnel**
1. **Reports** → **Acquisition** → **User Journey**
2. Understand:
   - Where visitors come from
   - What pages they visit
   - Which events they trigger
   - Drop-off points

### 4. **Geographic Data**
1. **Reports** → **Audience** → **Geographic**
2. See visitor locations (helps with marketing)
3. Amsterdam should be your primary city

### 5. **Device & Browser**
1. **Reports** → **Audience** → **Devices**
2. Mobile vs Desktop usage
3. Optimize for dominant platform

---

## Key Metrics to Monitor

### Monthly Health Check
- **Sessions:** Total visitor sessions (target: 100+ per month)
- **Users:** Unique visitors (target: 50+ per month)
- **Bounce Rate:** % of visitors who leave without action (target: <60%)
- **Avg. Session Duration:** How long people stay (target: >2 min)
- **Chatbot Opens:** How many click the chat (target: 10-20% of sessions)
- **Bookings Completed:** Conversion rate (target: 5-10% of chatbot opens)

### Conversion Funnel Ratio
```
100 sessions
  ↓ (20%) 
20 chatbot opens
  ↓ (25%)
5 booking sessions started
  ↓ (80%)
4 payments completed ✅
```

---

## Goal Setup (Optional)

To set conversion goals in Google Analytics:

1. Go to **Admin** (gear icon) → **Goals**
2. Click **Create Goal**
3. Set up these goals:

**Goal 1: Chatbot Engagement**
- Name: "Chatbot Opened"
- Type: Event
- Event Name: `chatbot_opened`
- Value: 1

**Goal 2: Booking Initiated**
- Name: "Booking Started"
- Type: Event
- Event Name: `booking_session_started`
- Value: 1

**Goal 3: Payment Converted** (Most important)
- Name: "Booking Completed"
- Type: Event
- Event Name: `booking_payment_completed`
- Value: 1

Once set up, Google shows conversion rates automatically! 📊

---

## Custom Reports (Advanced)

### Create a Dashboard
1. **Create New** → **Dashboard**
2. Add these widgets:
   - **Total Users** (metric)
   - **Total Events** (by chatbot_opened, booking_payment_completed)
   - **Conversion Rate** (booking_payment_completed / chatbot_opened)
   - **Geographic Map** (where users are from)
   - **Device Category** (mobile vs desktop)

---

## Privacy & GDPR Compliance

✅ **Anonymization Enabled**
- IP addresses anonymized automatically
- Cookie flags set to SameSite=None;Secure
- No personally identifiable data collected

✅ **Compliance**
- Analytics follows GDPR guidelines
- Users can opt-out via browser settings
- Data retention: 14 months (default Google setting)

---

## Troubleshooting

### "No Events Showing"
1. Wait 24-48 hours (takes time for data collection)
2. Open your website in a new incognito window
3. Click chatbot, trigger events
4. Check **Real-Time** dashboard (shows within seconds)

### "Low Traffic"
- Site is new (takes 1-2 weeks to appear in search)
- Share links on social media
- Email friends/network about Sauvage

### "Bounce Rate Too High"
- Improve page load speed
- Better call-to-action for chatbot
- More engaging content/images

---

## Monthly Reporting

Create a simple monthly report:

```markdown
# Sauvage Analytics - [Month]

## Traffic
- Sessions: [number]
- Users: [number]
- Avg. Session Duration: [time]

## Engagement
- Chatbot Opens: [number]
- Booking Sessions: [number]
- Payments Completed: [number] ✅

## Conversion Rate
- Chatbot Open Rate: [%]
- Booking Completion Rate: [%]

## Top Traffic Sources
1. [Source 1]: [%]
2. [Source 2]: [%]
3. [Source 3]: [%]

## Top Pages
1. [Page 1]: [views]
2. [Page 2]: [views]
3. [Page 3]: [views]
```

---

## Integration with Other Tools

### Shopify Integration (Optional)
If you want to track Shopify orders in Google Analytics:
- Go to Shopify → Analytics → Google Analytics
- Link your Google Analytics property
- Automatically tracks purchase events

### Email Marketing Integration (Optional)
- Track which emails drive most traffic
- UTM parameters: `utm_source=email&utm_medium=newsletter&utm_campaign=april`
- Example: `https://sauvage.amsterdam/?utm_source=email&utm_medium=newsletter&utm_campaign=easter`

---

## Best Practices

✅ **Check Analytics Monthly** - Understand your audience
✅ **Share Reports** - Send monthly summaries to Dorian/team
✅ **Act on Data** - If bounce rate high, improve content
✅ **Track Seasonality** - Note busy periods (weekends, holidays)
✅ **A/B Test** - Try different chatbot messages, see what converts best
✅ **Monitor Competitions** - If competitor bookings rise, react

---

**Last Updated:** April 5, 2026
**Measurement ID:** G-P99Q9D5EJ4
