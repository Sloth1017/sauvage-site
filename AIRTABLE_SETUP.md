# Airtable Automation Setup - Booking Notifications

## Step 1: Add "Calendar Link" Field to Airtable

1. Open your Airtable base: https://airtable.com/app4rCwUqnJ5A28YH
2. Go to the **Inquiries** table
3. Click the **+** icon to add a new field
4. **Field name:** `calendar_link`
5. **Field type:** URL
6. Save

This field will store the Google Calendar event link automatically.

---

## Step 2: Set Up the Notification Automation

1. Go to **Automations** tab (top menu)
2. Click **Create automation** (or edit existing one)
3. **Trigger:** "When a record is created"
4. **Table:** Inquiries
5. **Action:** "Send an email"

### Email Configuration

**To:** your@email.com

**Subject:**
```
🎉 New Booking Alert: {client_name} - {event_type}
```

**Body:**
```
Congrats Sauvage DAO 🎉

Someone booked an event via the Sauvage Chatbot!

Please communicate to the other DAO members if you would like to host this event.

Details Below:

Client: {client_name}
Event: {event_type}
Date: {dates}
Time: {start_time} - {end_time}
Guests: {guest_count}
Email: {email}
Phone: {phone}
Rooms: {rooms}

📅 Calendar Link: {calendar_link}

This is an automated reply. Please do not respond.
```

6. Click **Save automation**
7. Toggle to **ON**

---

## How It Works

1. ✅ User books through chatbot
2. ✅ Chatbot creates event in Google Calendar
3. ✅ Google Calendar returns event link
4. ✅ Chatbot saves link to Airtable `calendar_link` field
5. ✅ Airtable automation triggers
6. ✅ Email sent to you with full details + calendar link

---

## Testing

1. Go to https://sauvage.amsterdam
2. Open chatbot bubble
3. Complete a test booking
4. Check your email in 30 seconds

You should receive the notification with the Google Calendar link!

---

## Customization

You can customize the email further:
- Add more Airtable fields (add-ons, customer type, notes)
- Change the subject line
- Add formatting or additional context
- Send to multiple team members (separate by comma)

---

**Last Updated:** April 4, 2026
