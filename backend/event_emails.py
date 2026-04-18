"""
event_emails.py
---------------
Three lifecycle emails sent around every confirmed booking:

  1. day_before  — sent the morning before the event (~09:00)
                   Reminder, T&C recap, house rules, host WhatsApp
  2. day_of      — sent the morning of the event (~08:00)
                   "Today's the day", final logistics, host WhatsApp
  3. day_after   — sent the morning after the event (~10:00)
                   Thank-you + feedback request (best-practice format)

All three are branded with the Sauvage gold/black palette and logo.
The attributed host's WhatsApp link is injected into emails 1 and 2.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── SMTP config (shared with confirmation_email.py) ──────────────────────────
SMTP_SERVER   = os.getenv("SMTP_SERVER",   "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER",     "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL    = os.getenv("FROM_EMAIL",    "bookings@sauvage.amsterdam")
BASE_URL      = os.getenv("BASE_URL",      "https://sauvage.amsterdam")

# ── Host directory ────────────────────────────────────────────────────────────
_HOSTS = {
    "Greg":    {"name": "Greg",   "whatsapp": "31634742988",  "display": "+31 6 3474 2988"},
    "Dorian":  {"name": "Dorian", "whatsapp": "31643734908",  "display": "+31 6 4373 4908"},
    "Bart":    {"name": "Bart",   "whatsapp": "31641359923",  "display": "+31 6 4135 9923"},
}
_DEFAULT_HOST = _HOSTS["Greg"]

LOGO_URL  = f"{BASE_URL}/media/sauvage-logo.png"
TERMS_URL = f"{BASE_URL}/terms"


# ── Shared helpers ────────────────────────────────────────────────────────────

def _host_info(attributed_host: str) -> dict:
    """Return host dict for a given attributed host name, or Greg as fallback."""
    if not attributed_host:
        return _DEFAULT_HOST
    for key in _HOSTS:
        if key.lower() in attributed_host.lower():
            return _HOSTS[key]
    return _DEFAULT_HOST


def _fmt_rooms(rooms) -> str:
    if isinstance(rooms, list):
        return " + ".join(rooms)
    return str(rooms or "Sauvage Space")


def _fmt_date(dates) -> str:
    if isinstance(dates, list):
        return dates[0] if dates else ""
    return str(dates or "")


def _base_html(content: str, preheader: str = "") -> str:
    """Wrap content in the standard Sauvage email shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sauvage Space</title>
</head>
<body style="margin:0;padding:0;background:#f5f3ef;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;color:#1a1a1a;">
  {"<span style='display:none;max-height:0;overflow:hidden;'>" + preheader + "</span>" if preheader else ""}
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f5f3ef;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;width:100%;background:#ffffff;border-radius:4px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background:#1a1a1a;padding:28px 40px 24px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="vertical-align:middle;">
                    <img src="{LOGO_URL}" alt="Sauvage Space" width="60" height="60"
                         style="display:block;width:60px;height:60px;border:0;filter:invert(1);" />
                  </td>
                  <td style="vertical-align:middle;padding-left:18px;">
                    <p style="margin:0 0 3px;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#666;font-weight:500;">Potgieterstraat 47H, Amsterdam</p>
                    <p style="margin:0;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#b8860b;font-weight:600;">Sauvage Space</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Gold stripe -->
          <tr><td style="background:#b8860b;height:3px;font-size:0;line-height:0;">&nbsp;</td></tr>

          <!-- Body -->
          {content}

          <!-- Gold stripe -->
          <tr><td style="background:#b8860b;height:2px;font-size:0;line-height:0;">&nbsp;</td></tr>

          <!-- Footer -->
          <tr>
            <td style="background:#111111;padding:22px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="vertical-align:middle;">
                    <img src="{LOGO_URL}" alt="" width="30" height="30"
                         style="display:inline-block;width:30px;height:30px;border:0;filter:invert(1);opacity:0.6;vertical-align:middle;" />
                    <span style="font-size:11px;color:#555;margin-left:10px;vertical-align:middle;letter-spacing:1px;text-transform:uppercase;">Sauvage Space</span>
                  </td>
                  <td align="right" style="vertical-align:middle;">
                    <p style="margin:0;font-size:11px;color:#555;line-height:1.5;">
                      <a href="https://sauvage.amsterdam" style="color:#888;text-decoration:none;">sauvage.amsterdam</a>
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send(to_email: str, subject: str, html: str, plain: str) -> bool:
    """Send an email via SMTP. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[EventEmail] SMTP not configured — skipping: {subject}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Sauvage Space <{FROM_EMAIL}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html,  "html"))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"[EventEmail] Sent '{subject}' to {to_email}")
        return True
    except Exception as e:
        print(f"[EventEmail] Failed to send '{subject}' to {to_email}: {e}")
        return False


# ── ① DAY BEFORE ─────────────────────────────────────────────────────────────

def send_day_before(state: dict) -> bool:
    """
    Reminder email sent the morning before the event.
    Covers: event details, house rules, T&C reminder, host WhatsApp.
    """
    client_name    = state.get("client_name", "there")
    client_email   = state.get("email", "")
    event_type     = state.get("event_type", "event")
    date_str       = _fmt_date(state.get("dates"))
    start_time     = state.get("start_time", "")
    end_time       = state.get("end_time", "")
    rooms_str      = _fmt_rooms(state.get("rooms"))
    guest_count    = state.get("guest_count", "")
    attributed     = state.get("attributed_host", "")
    arrival_time   = state.get("arrival_time", "")

    if not client_email:
        return False

    host      = _host_info(attributed)
    time_str  = f"{start_time} to {end_time}" if start_time and end_time else start_time or "see booking"
    wa_link   = f"https://wa.me/{host['whatsapp']}"
    first     = client_name.split()[0]

    subject = f"Your {event_type} at Sauvage is tomorrow"

    arrival_block = ""
    if arrival_time:
        arrival_block = f"""<tr>
          <td style="padding:0 40px 28px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0"
                   style="background:#f5f3ef;border-radius:3px;padding:16px 20px;">
              <tr>
                <td>
                  <p style="margin:0 0 4px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Arrival for setup</p>
                  <p style="margin:0;font-size:15px;font-weight:600;color:#1a1a1a;">{arrival_time}</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    content = f"""
          <!-- Heading -->
          <tr>
            <td style="padding:36px 40px 8px;">
              <p style="margin:0 0 12px;font-size:16px;line-height:1.6;color:#1a1a1a;">Hi {first},</p>
              <p style="margin:0;font-size:16px;line-height:1.6;color:#333;">
                Just a heads-up that your <strong>{event_type}</strong> at Sauvage is <strong>tomorrow</strong>. We're looking forward to hosting you.
              </p>
            </td>
          </tr>

          <!-- Booking snapshot -->
          <tr>
            <td style="padding:24px 40px 28px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:#f5f3ef;border-radius:4px;padding:24px;">
                <tr><td style="padding:0 4px;">
                  <p style="margin:0 0 16px;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#999;font-weight:600;">Your booking</p>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                        <p style="margin:0 0 2px;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Date</p>
                        <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">{date_str}</p>
                      </td>
                      <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                        <p style="margin:0 0 2px;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Time</p>
                        <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">{time_str}</p>
                      </td>
                    </tr>
                    <tr>
                      <td width="50%" style="vertical-align:top;">
                        <p style="margin:0 0 2px;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Space</p>
                        <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">{rooms_str}</p>
                      </td>
                      <td width="50%" style="vertical-align:top;">
                        <p style="margin:0 0 2px;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Guests</p>
                        <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">{guest_count}</p>
                      </td>
                    </tr>
                  </table>
                </td></tr>
              </table>
            </td>
          </tr>

          {arrival_block}

          <!-- House rules -->
          <tr>
            <td style="padding:0 40px 28px;">
              <h2 style="margin:0 0 14px;font-size:13px;letter-spacing:1.5px;text-transform:uppercase;color:#999;font-weight:600;">A few things to keep in mind</h2>
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td width="22" style="vertical-align:top;padding-top:1px;">
                    <span style="display:inline-block;width:6px;height:6px;background:#b8860b;border-radius:50%;margin-top:6px;"></span>
                  </td>
                  <td style="font-size:14px;line-height:1.7;color:#333;padding-bottom:8px;">
                    Sauvage is a shared community space. Other residents — Ikinari Coffee, the Gallery, Fento kitchen, and Selection Sauvage wines — may be present. Please stay within your booked areas.
                  </td>
                </tr>
                <tr>
                  <td width="22" style="vertical-align:top;padding-top:1px;">
                    <span style="display:inline-block;width:6px;height:6px;background:#b8860b;border-radius:50%;margin-top:6px;"></span>
                  </td>
                  <td style="font-size:14px;line-height:1.7;color:#333;padding-bottom:8px;">
                    Please leave every space exactly as you found it. The closing checklist takes about 15 minutes and keeps things running smoothly for everyone.
                  </td>
                </tr>
                <tr>
                  <td width="22" style="vertical-align:top;padding-top:1px;">
                    <span style="display:inline-block;width:6px;height:6px;background:#b8860b;border-radius:50%;margin-top:6px;"></span>
                  </td>
                  <td style="font-size:14px;line-height:1.7;color:#333;padding-bottom:8px;">
                    Music must be turned off and guests out by your agreed end time.
                  </td>
                </tr>
                <tr>
                  <td width="22" style="vertical-align:top;padding-top:1px;">
                    <span style="display:inline-block;width:6px;height:6px;background:#b8860b;border-radius:50%;margin-top:6px;"></span>
                  </td>
                  <td style="font-size:14px;line-height:1.7;color:#333;">
                    Your booking is subject to our full <a href="{TERMS_URL}" style="color:#1a1a1a;font-weight:600;text-decoration:underline;">Terms &amp; Conditions</a>.
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Host contact -->
          <tr>
            <td style="padding:0 40px 36px;">
              <hr style="border:none;border-top:1px solid #e8e4de;margin:0 0 24px;">
              <h2 style="margin:0 0 10px;font-size:13px;letter-spacing:1.5px;text-transform:uppercase;color:#999;font-weight:600;">Your host tomorrow</h2>
              <p style="margin:0 0 16px;font-size:14px;line-height:1.7;color:#333;">
                {host['name']} will be your point of contact. For any questions or last-minute needs, reach them directly on WhatsApp:
              </p>
              <a href="{wa_link}"
                 style="display:inline-block;background:#1a1a1a;color:#ffffff;text-decoration:none;
                        padding:13px 26px;border-radius:2px;font-size:12px;font-weight:600;
                        letter-spacing:1px;text-transform:uppercase;border-left:3px solid #b8860b;">
                WhatsApp {host['name']} &rarr;
              </a>
              <p style="margin:12px 0 0;font-size:12px;color:#aaa;">{host['display']}</p>
            </td>
          </tr>"""

    html = _base_html(content, preheader=f"Your {event_type} at Sauvage is tomorrow — here's everything you need.")

    plain = f"""Hi {first},

Just a heads-up that your {event_type} at Sauvage is tomorrow. We're looking forward to hosting you.

YOUR BOOKING
Date:   {date_str}
Time:   {time_str}
Space:  {rooms_str}
Guests: {guest_count}
{"Arrival for setup: " + arrival_time if arrival_time else ""}

A FEW THINGS TO KEEP IN MIND
- Sauvage is a shared community space. Please stay within your booked areas.
- Leave every space exactly as you found it. The closing checklist takes about 15 minutes.
- Music off and guests out by your agreed end time.
- Your booking is subject to our Terms & Conditions: {TERMS_URL}

YOUR HOST TOMORROW
{host['name']} is your point of contact for anything you need.
WhatsApp: {wa_link}  ({host['display']})

See you tomorrow,
Sauvage Space
sauvage.amsterdam
"""
    return _send(client_email, subject, html, plain)


# ── ② DAY OF ─────────────────────────────────────────────────────────────────

def send_day_of(state: dict) -> bool:
    """
    Morning-of email sent the day of the event.
    Covers: event is today, key logistics, host WhatsApp.
    """
    client_name    = state.get("client_name", "there")
    client_email   = state.get("email", "")
    event_type     = state.get("event_type", "event")
    date_str       = _fmt_date(state.get("dates"))
    start_time     = state.get("start_time", "")
    end_time       = state.get("end_time", "")
    rooms_str      = _fmt_rooms(state.get("rooms"))
    guest_count    = state.get("guest_count", "")
    attributed     = state.get("attributed_host", "")
    arrival_time   = state.get("arrival_time", "")

    if not client_email:
        return False

    host      = _host_info(attributed)
    time_str  = f"{start_time} to {end_time}" if start_time and end_time else start_time or "see booking"
    wa_link   = f"https://wa.me/{host['whatsapp']}"
    first     = client_name.split()[0]

    subject = f"Today's the day - your {event_type} at Sauvage"

    content = f"""
          <!-- Heading -->
          <tr>
            <td style="padding:36px 40px 8px;">
              <p style="margin:0 0 12px;font-size:16px;line-height:1.6;color:#1a1a1a;">Hi {first},</p>
              <p style="margin:0 0 14px;font-size:16px;line-height:1.6;color:#333;">
                Today's the day! Your <strong>{event_type}</strong> at Sauvage starts at <strong>{start_time or "your booked time"}</strong>. We hope everything goes beautifully.
              </p>
              <p style="margin:0;font-size:15px;line-height:1.6;color:#555;">
                Here's a quick summary of your booking for reference:
              </p>
            </td>
          </tr>

          <!-- Booking snapshot -->
          <tr>
            <td style="padding:20px 40px 28px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:#f5f3ef;border-radius:4px;padding:22px 24px;">
                <tr><td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                        <p style="margin:0 0 2px;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Time</p>
                        <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:600;">{time_str}</p>
                      </td>
                      <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                        <p style="margin:0 0 2px;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Space</p>
                        <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">{rooms_str}</p>
                      </td>
                    </tr>
                    {"<tr><td colspan='2'><p style='margin:0 0 2px;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;'>Arrival for setup</p><p style='margin:0;font-size:14px;color:#1a1a1a;font-weight:500;'>" + arrival_time + "</p></td></tr>" if arrival_time else ""}
                  </table>
                </td></tr>
              </table>
            </td>
          </tr>

          <!-- Quick reminders -->
          <tr>
            <td style="padding:0 40px 28px;">
              <h2 style="margin:0 0 12px;font-size:13px;letter-spacing:1.5px;text-transform:uppercase;color:#999;font-weight:600;">Quick reminders</h2>
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td width="22" style="vertical-align:top;">
                    <span style="display:inline-block;width:6px;height:6px;background:#b8860b;border-radius:50%;margin-top:7px;"></span>
                  </td>
                  <td style="font-size:14px;line-height:1.7;color:#333;padding-bottom:7px;">
                    Stay within your booked areas and treat the shared spaces with care.
                  </td>
                </tr>
                <tr>
                  <td width="22" style="vertical-align:top;">
                    <span style="display:inline-block;width:6px;height:6px;background:#b8860b;border-radius:50%;margin-top:7px;"></span>
                  </td>
                  <td style="font-size:14px;line-height:1.7;color:#333;padding-bottom:7px;">
                    Run through the closing checklist before you leave — it takes about 15 minutes.
                  </td>
                </tr>
                <tr>
                  <td width="22" style="vertical-align:top;">
                    <span style="display:inline-block;width:6px;height:6px;background:#b8860b;border-radius:50%;margin-top:7px;"></span>
                  </td>
                  <td style="font-size:14px;line-height:1.7;color:#333;">
                    End time is <strong>{end_time or "as agreed"}</strong> — music off and all guests out by then.
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Host contact -->
          <tr>
            <td style="padding:0 40px 36px;">
              <hr style="border:none;border-top:1px solid #e8e4de;margin:0 0 22px;">
              <p style="margin:0 0 6px;font-size:13px;letter-spacing:1.5px;text-transform:uppercase;color:#999;font-weight:600;">Need anything today?</p>
              <p style="margin:0 0 16px;font-size:14px;line-height:1.7;color:#333;">
                {host['name']} is your host today. Message them directly on WhatsApp for anything — access, questions, or last-minute requests:
              </p>
              <a href="{wa_link}"
                 style="display:inline-block;background:#1a1a1a;color:#ffffff;text-decoration:none;
                        padding:13px 26px;border-radius:2px;font-size:12px;font-weight:600;
                        letter-spacing:1px;text-transform:uppercase;border-left:3px solid #b8860b;">
                WhatsApp {host['name']} &rarr;
              </a>
              <p style="margin:12px 0 0;font-size:12px;color:#aaa;">{host['display']}</p>
            </td>
          </tr>

          <!-- Sign off -->
          <tr>
            <td style="padding:0 40px 36px;">
              <p style="margin:0;font-size:15px;line-height:1.7;color:#333;">
                Have a wonderful {event_type}. We're glad you're here.
              </p>
            </td>
          </tr>"""

    html = _base_html(content, preheader=f"Today's the day! Your {event_type} starts at {start_time}.")

    plain = f"""Hi {first},

Today's the day! Your {event_type} at Sauvage starts at {start_time or "your booked time"}.

YOUR BOOKING TODAY
Time:   {time_str}
Space:  {rooms_str}
{"Arrival for setup: " + arrival_time if arrival_time else ""}

QUICK REMINDERS
- Stay within your booked areas.
- Run through the closing checklist before you leave.
- End time is {end_time or "as agreed"} — music off and guests out by then.

NEED ANYTHING TODAY?
{host['name']} is your host. Message them on WhatsApp:
{wa_link}  ({host['display']})

Have a wonderful {event_type}.

Sauvage Space
sauvage.amsterdam
"""
    return _send(client_email, subject, html, plain)


# ── ③ DAY AFTER (feedback) ────────────────────────────────────────────────────

def send_day_after(state: dict) -> bool:
    """
    Feedback email sent the morning after the event.
    Designed to maximise response rate and actionable insight:
    - Personal, warm tone
    - Three focused questions (overall, standout, improve)
    - Simple reply mechanism — no external form needed
    - Net Promoter-style opener to quantify satisfaction
    """
    client_name    = state.get("client_name", "there")
    client_email   = state.get("email", "")
    event_type     = state.get("event_type", "event")
    attributed     = state.get("attributed_host", "")

    if not client_email:
        return False

    host      = _host_info(attributed)
    first     = client_name.split()[0]
    reply_url = f"mailto:{FROM_EMAIL}?subject=Feedback%20from%20{first}&body=Hi%20Sauvage%20team%2C%0A%0A"

    subject = f"How did your {event_type} go? A quick word from Sauvage"

    content = f"""
          <!-- Heading -->
          <tr>
            <td style="padding:36px 40px 8px;">
              <p style="margin:0 0 12px;font-size:16px;line-height:1.6;color:#1a1a1a;">Hi {first},</p>
              <p style="margin:0 0 14px;font-size:16px;line-height:1.6;color:#333;">
                We hope your <strong>{event_type}</strong> was everything you wanted it to be. Thank you for trusting Sauvage with your event — it means a lot to us.
              </p>
              <p style="margin:0;font-size:15px;line-height:1.6;color:#555;">
                We read every piece of feedback personally. It takes less than two minutes and genuinely shapes how we improve the space. Would you mind sharing a few thoughts?
              </p>
            </td>
          </tr>

          <!-- Feedback questions -->
          <tr>
            <td style="padding:24px 40px 28px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:#f5f3ef;border-radius:4px;overflow:hidden;">

                <!-- Q1 -->
                <tr>
                  <td style="padding:20px 24px 16px;border-bottom:1px solid #e8e4de;">
                    <p style="margin:0 0 6px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#b8860b;font-weight:600;">Question 1 of 3</p>
                    <p style="margin:0 0 10px;font-size:15px;font-weight:600;color:#1a1a1a;line-height:1.5;">
                      On a scale of 1-10, how would you rate your overall experience at Sauvage?
                    </p>
                    <p style="margin:0;font-size:12px;color:#999;">Just hit reply and include your rating — 1 (not great) to 10 (exceptional).</p>
                  </td>
                </tr>

                <!-- Q2 -->
                <tr>
                  <td style="padding:20px 24px 16px;border-bottom:1px solid #e8e4de;">
                    <p style="margin:0 0 6px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#b8860b;font-weight:600;">Question 2 of 3</p>
                    <p style="margin:0 0 10px;font-size:15px;font-weight:600;color:#1a1a1a;line-height:1.5;">
                      What was the highlight of the event for you — something we got right?
                    </p>
                    <p style="margin:0;font-size:12px;color:#999;">Could be the space, the process, the host, the add-ons — anything.</p>
                  </td>
                </tr>

                <!-- Q3 -->
                <tr>
                  <td style="padding:20px 24px 20px;">
                    <p style="margin:0 0 6px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#b8860b;font-weight:600;">Question 3 of 3</p>
                    <p style="margin:0 0 10px;font-size:15px;font-weight:600;color:#1a1a1a;line-height:1.5;">
                      Is there anything we could have done better or made easier for you?
                    </p>
                    <p style="margin:0;font-size:12px;color:#999;">No detail is too small — we genuinely want to know.</p>
                  </td>
                </tr>

              </table>
            </td>
          </tr>

          <!-- CTA -->
          <tr>
            <td style="padding:0 40px 32px;text-align:center;">
              <a href="{reply_url}"
                 style="display:inline-block;background:#1a1a1a;color:#ffffff;text-decoration:none;
                        padding:14px 32px;border-radius:2px;font-size:12px;font-weight:600;
                        letter-spacing:1px;text-transform:uppercase;border-left:3px solid #b8860b;">
                Reply with your feedback &rarr;
              </a>
              <p style="margin:14px 0 0;font-size:12px;color:#aaa;">
                Or just hit reply to this email — it goes straight to {host['name']}.
              </p>
            </td>
          </tr>

          <!-- Sign off -->
          <tr>
            <td style="padding:0 40px 36px;">
              <hr style="border:none;border-top:1px solid #e8e4de;margin:0 0 22px;">
              <p style="margin:0 0 10px;font-size:14px;line-height:1.7;color:#333;">
                Thank you again, {first}. We'd love to have you back at Sauvage.
              </p>
              <p style="margin:0;font-size:14px;color:#555;">
                Warm regards,<br>
                <strong>{host['name']} &amp; the Sauvage team</strong>
              </p>
            </td>
          </tr>"""

    html = _base_html(content, preheader=f"Two minutes to help us improve — how did your {event_type} go?")

    plain = f"""Hi {first},

We hope your {event_type} was everything you wanted it to be. Thank you for trusting Sauvage with your event.

We read every piece of feedback personally. Three quick questions — takes less than two minutes:

Q1: On a scale of 1-10, how would you rate your overall experience at Sauvage?

Q2: What was the highlight of the event for you — something we got right?

Q3: Is there anything we could have done better or made easier for you?

Just hit reply and share your thoughts — it goes straight to {host['name']}.

Thank you again. We'd love to have you back.

{host['name']} & the Sauvage team
sauvage.amsterdam
"""
    return _send(client_email, subject, html, plain)
