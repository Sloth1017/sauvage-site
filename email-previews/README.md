# Email Preview Collection

This folder contains HTML previews for all emails in the Sauvage Space booking flow.

## 📧 Email Flow

1. **Booking Confirmation** (`1_confirmation.html`)
   - Sent immediately after payment
   - Includes booking summary, calendar links, invoice, and arrival time form
   - Customized for wine tastings vs regular events

2. **Day Before Reminder** (`2_day_before.html`)
   - Sent the morning before (~9:00 AM)
   - Location details, WiFi info, host contact, last-minute checklist
   - Includes Google Maps link and weather considerations

3. **Day Of Event** (`3_day_of.html`)
   - Sent the morning of (~8:00 AM)
   - Time reminder, host WhatsApp contact, parking info
   - Direct access to location map

4. **Day After Follow-up** (`4_day_after.html`)
   - Sent the morning after (~10:00 AM)
   - Thank you message, feedback form, wine selection upsell
   - Request for testimonial/photos

## 🚀 Quick Start

### View All Previews
1. Open `index.html` in your browser - a beautiful dashboard to navigate all emails
2. Click any email card to open the full HTML preview

### Generate Fresh Previews
If you modify any email templates in the backend, regenerate previews:

```bash
python3 generate_email_previews.py
```

This will:
- Create fresh HTML files from the current email templates
- Embed all images (logo, calendar icons) as base64 data URIs
- Generate realistic sample data for preview

## 🎨 Customization

### Change Preview Data
Edit the `STATE` variable in `generate_email_previews.py`:

```python
STATE = {
    "client_name":    "Your Name",
    "email":          "your@email.com",
    "event_type":     "Your Event",
    "dates":          "2026-05-10",
    "start_time":     "18:00",
    "end_time":       "23:00",
    "rooms":          ["Room Names"],
    "guest_count":    20,
    "attributed_host":"Greg",
    "arrival_time":   "16:00",
}
```

Then regenerate:
```bash
python3 generate_email_previews.py
```

### Add More Guest Variations
The preview currently uses one sample guest. To create previews with different:
- Multiple events
- Different room configurations
- Team/wine event variations

Modify the script to loop through different STATE variants.

## 📋 Email Template Files

The actual email templates are in the `../backend/` directory:

- `confirmation_email.py` - Booking confirmation template & sending logic
- `event_emails.py` - Day before, day of, day after templates
- `calendar_links.py` - Google Calendar & iCal link generation

## 🔧 Technical Details

### Image Embedding
All images (logo, calendar icons) are embedded as base64 data URIs, so:
- ✅ Emails render perfectly with images even offline
- ✅ No external image dependencies
- ✅ Browser-safe for testing in isolation

### Sample Booking
All previews use the same sample guest to ensure consistency:
- **Name:** Anna Schmidt
- **Event:** Birthday
- **Date:** May 10, 2026
- **Time:** 6:00 PM - 11:00 PM
- **Guests:** 25
- **Rooms:** Upstairs (Gallery) + Entrance

## 📧 Email Branding

All emails follow the Sauvage brand guidelines:
- **Colors:** Ink (#1a1a18), Cream (#f7f4ef), Gold (#F5F1E6), Warm (#8b6f47)
- **Fonts:** Georgia serif for body, Helvetica for UI text
- **Layout:** 600px width, responsive on mobile
- **Design:** Matches sauvage.amsterdam exactly

## 🔐 Security Notes

- Preview links use `file://` URLs for local testing
- Real emails use proper links and security tokens
- Arrival time form uses HMAC-SHA256 token validation in production
- No test data is sent to production services

## 📞 Support

For questions about specific email:
1. Open the corresponding HTML file
2. Check the backend Python file for the template
3. Review `calendar_links.py` for URL generation logic

---

**Last Generated:** April 23, 2026
