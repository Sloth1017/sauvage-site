"""
event_emails.py
---------------
Three lifecycle emails sent around every confirmed booking:

  1. day_before  — sent the morning before the event (~09:00)
  2. day_of      — sent the morning of the event (~08:00)
  3. day_after   — sent the morning after the event (~10:00)

Branding matches sauvage.amsterdam exactly:
  --ink:    #1a1a18   headers, CTAs, dark text
  --cream:  #f7f4ef   email background
  --gold:   #F5F1E6   card / panel backgrounds
  --warm:   #8b6f47   accent stripe, labels, bullet dots
  --muted:  #6b6560   secondary text
  Font:     Georgia serif (Plein fallback for web; Georgia is the closest
            widely-supported serif for email clients)
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── SMTP config ───────────────────────────────────────────────────────────────
SMTP_SERVER   = os.getenv("SMTP_SERVER",   "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER",     "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL    = os.getenv("FROM_EMAIL",    "bookings@sauvage.amsterdam")
BASE_URL      = os.getenv("BASE_URL",      "https://sauvage.amsterdam")

# ── Embedded logos (base64 PNG — no external URL dependency) ─────────────────
# White version: for dark ink header background
_LOGO_WHITE = "data:image/png;base64,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"
# Dark version: for light cream backgrounds (footer etc.)
_LOGO_DARK  = "data:image/png;base64,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"

# ── Brand tokens (matches sauvage.amsterdam CSS variables) ────────────────────
C_INK    = "#1a1a18"
C_CREAM  = "#f7f4ef"
C_GOLD   = "#F5F1E6"   # card backgrounds — the site's "--gold"
C_WARM   = "#8b6f47"   # accent colour — the site's "--warm"
C_MUTED  = "#6b6560"
C_BORDER = "rgba(26,26,24,0.10)"
C_WHITE  = "#ffffff"

TERMS_URL = f"{BASE_URL}/terms"

# ── Host directory ────────────────────────────────────────────────────────────
_HOSTS = {
    "Greg":   {"name": "Greg",   "whatsapp": "31634742988",  "display": "+31 6 3474 2988"},
    "Dorian": {"name": "Dorian", "whatsapp": "31643734908",  "display": "+31 6 4373 4908"},
    "Bart":   {"name": "Bart",   "whatsapp": "31641359923",  "display": "+31 6 4135 9923"},
}
_DEFAULT_HOST = _HOSTS["Greg"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _host_info(attributed_host: str) -> dict:
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


# ── Shared shell ──────────────────────────────────────────────────────────────

def _shell(body_rows: str, preheader: str = "") -> str:
    """
    Wraps rows in the Sauvage email shell.
    Header: dark ink background, logo left, wordmark right.
    Footer: cream background, muted links.
    """
    pre = (
        f'<div style="display:none;max-height:0;overflow:hidden;'
        f'font-size:1px;color:{C_CREAM};">{preheader}&nbsp;</div>'
        if preheader else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Sauvage Space</title>
</head>
<body style="margin:0;padding:0;background:{C_CREAM};
             font-family:Georgia,'Times New Roman',serif;
             color:{C_INK};-webkit-text-size-adjust:100%;">
{pre}
<!-- Outer wrapper -->
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{C_CREAM};padding:40px 0 60px;">
  <tr><td align="center">

    <!-- Email card -->
    <table width="600" cellpadding="0" cellspacing="0" border="0"
           style="max-width:600px;width:100%;background:{C_WHITE};
                  border-radius:2px;overflow:hidden;">

      <!-- ── HEADER ── -->
      <tr>
        <td style="background:{C_INK};padding:32px 44px 28px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <!-- Logo mark -->
              <td width="56" style="vertical-align:middle;">
                <img src="{_LOGO_WHITE}" alt="Sauvage" width="56" height="56"
                     style="display:block;border:0;" />
              </td>
              <!-- Wordmark -->
              <td style="vertical-align:middle;padding-left:16px;">
                <p style="margin:0;font-family:Georgia,serif;font-size:22px;
                           font-weight:300;font-style:italic;
                           letter-spacing:0.08em;color:{C_WHITE};line-height:1;">
                  Sauvage
                </p>
                <p style="margin:3px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                           font-size:9px;letter-spacing:0.22em;text-transform:uppercase;
                           color:{C_WARM};font-weight:400;">
                  Amsterdam
                </p>
              </td>
              <!-- Address -->
              <td align="right" style="vertical-align:middle;">
                <p style="margin:0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                           font-size:9px;letter-spacing:0.14em;text-transform:uppercase;
                           color:rgba(255,255,255,0.35);line-height:1.6;">
                  Potgieterstraat 47H<br>Amsterdam
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Warm accent stripe -->
      <tr>
        <td style="background:{C_WARM};height:2px;font-size:0;line-height:0;">&nbsp;</td>
      </tr>

      <!-- ── BODY ROWS ── -->
      {body_rows}

      <!-- Warm accent stripe -->
      <tr>
        <td style="background:{C_WARM};height:1px;font-size:0;line-height:0;">&nbsp;</td>
      </tr>

      <!-- ── FOOTER ── -->
      <tr>
        <td style="background:{C_CREAM};padding:24px 44px 28px;
                   border-top:1px solid rgba(26,26,24,0.08);">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:11px;color:{C_MUTED};line-height:1.7;">
                <a href="https://sauvage.amsterdam"
                   style="color:{C_MUTED};text-decoration:none;
                          letter-spacing:0.06em;">sauvage.amsterdam</a>
                &nbsp;&middot;&nbsp;
                <a href="{TERMS_URL}"
                   style="color:{C_MUTED};text-decoration:none;">Terms &amp; Conditions</a>
              </td>
              <td align="right"
                  style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:10px;color:rgba(107,101,96,0.5);letter-spacing:0.08em;
                         text-transform:uppercase;">
                Sauvage DAO
              </td>
            </tr>
          </table>
        </td>
      </tr>

    </table>
    <!-- /email card -->

  </td></tr>
</table>
</body>
</html>"""


def _label(text: str) -> str:
    """Uppercase tracking label — matches site's section label style."""
    return (
        f'<p style="margin:0 0 10px;'
        f'font-family:\'Helvetica Neue\',Helvetica,Arial,sans-serif;'
        f'font-size:9px;letter-spacing:0.2em;text-transform:uppercase;'
        f'color:{C_WARM};font-weight:500;">{text}</p>'
    )


def _h1(text: str) -> str:
    return (
        f'<h1 style="margin:0;font-family:Georgia,\'Times New Roman\',serif;'
        f'font-size:28px;font-weight:300;font-style:italic;'
        f'letter-spacing:-0.01em;color:{C_INK};line-height:1.25;">{text}</h1>'
    )


def _booking_card(date_str, time_str, rooms_str, guest_count, arrival_time="") -> str:
    arrival_row = ""
    if arrival_time:
        arrival_row = f"""
                    <tr>
                      <td colspan="2" style="padding:10px 0 0;vertical-align:top;">
                        <p style="margin:0 0 3px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                   font-size:9px;letter-spacing:0.16em;text-transform:uppercase;color:{C_MUTED};">
                          Setup arrival</p>
                        <p style="margin:0;font-family:Georgia,serif;font-size:15px;
                                   font-weight:400;color:{C_INK};">{arrival_time}</p>
                      </td>
                    </tr>"""
    return f"""
          <tr>
            <td style="padding:0 44px 32px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:{C_GOLD};border-radius:2px;
                            border:1px solid rgba(26,26,24,0.08);">
                <tr>
                  <td style="padding:24px 28px;">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td width="50%" style="padding:0 0 14px;vertical-align:top;">
                          <p style="margin:0 0 3px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:9px;letter-spacing:0.16em;text-transform:uppercase;color:{C_MUTED};">Date</p>
                          <p style="margin:0;font-family:Georgia,serif;font-size:15px;
                                     font-weight:400;color:{C_INK};">{date_str}</p>
                        </td>
                        <td width="50%" style="padding:0 0 14px;vertical-align:top;">
                          <p style="margin:0 0 3px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:9px;letter-spacing:0.16em;text-transform:uppercase;color:{C_MUTED};">Time</p>
                          <p style="margin:0;font-family:Georgia,serif;font-size:15px;
                                     font-weight:400;color:{C_INK};">{time_str}</p>
                        </td>
                      </tr>
                      <tr>
                        <td width="50%" style="vertical-align:top;">
                          <p style="margin:0 0 3px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:9px;letter-spacing:0.16em;text-transform:uppercase;color:{C_MUTED};">Space</p>
                          <p style="margin:0;font-family:Georgia,serif;font-size:15px;
                                     font-weight:400;color:{C_INK};">{rooms_str}</p>
                        </td>
                        <td width="50%" style="vertical-align:top;">
                          <p style="margin:0 0 3px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:9px;letter-spacing:0.16em;text-transform:uppercase;color:{C_MUTED};">Guests</p>
                          <p style="margin:0;font-family:Georgia,serif;font-size:15px;
                                     font-weight:400;color:{C_INK};">{guest_count}</p>
                        </td>
                      </tr>
                      {arrival_row}
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def _cta_button(label: str, href: str) -> str:
    return (
        f'<a href="{href}" '
        f'style="display:inline-block;background:{C_INK};color:{C_WHITE};'
        f'text-decoration:none;padding:14px 30px;border-radius:1px;'
        f'font-family:\'Helvetica Neue\',Helvetica,Arial,sans-serif;'
        f'font-size:10px;font-weight:600;letter-spacing:0.18em;'
        f'text-transform:uppercase;">{label}</a>'
    )


def _bullet(text: str) -> str:
    return f"""
                <tr>
                  <td width="20" style="vertical-align:top;padding-top:5px;">
                    <span style="display:inline-block;width:4px;height:4px;
                                 background:{C_WARM};border-radius:50%;
                                 margin-top:7px;"></span>
                  </td>
                  <td style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                             font-size:14px;line-height:1.75;color:{C_MUTED};
                             padding-bottom:8px;">{text}</td>
                </tr>"""


def _send(to_email: str, subject: str, html: str, plain: str) -> bool:
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
        print(f"[EventEmail] Failed '{subject}' to {to_email}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# ① DAY BEFORE
# ─────────────────────────────────────────────────────────────────────────────

def send_day_before(state: dict) -> bool:
    client_name  = state.get("client_name", "there")
    client_email = state.get("email", "")
    event_type   = state.get("event_type", "event")
    date_str     = _fmt_date(state.get("dates"))
    start_time   = state.get("start_time", "")
    end_time     = state.get("end_time", "")
    rooms_str    = _fmt_rooms(state.get("rooms"))
    guest_count  = state.get("guest_count", "")
    attributed   = state.get("attributed_host", "")
    arrival_time = state.get("arrival_time", "")

    if not client_email:
        return False

    host     = _host_info(attributed)
    time_str = f"{start_time} to {end_time}" if start_time and end_time else start_time or "see booking"
    wa_link  = f"https://wa.me/{host['whatsapp']}"
    first    = client_name.split()[0]
    subject  = f"Your {event_type} at Sauvage — tomorrow"

    rows = f"""
          <!-- Intro -->
          <tr>
            <td style="padding:44px 44px 8px;">
              {_label("Reminder")}
              {_h1(f"Tomorrow at Sauvage")}
              <p style="margin:20px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:15px;line-height:1.75;color:{C_MUTED};">
                Hi {first} — your <strong style="color:{C_INK};">{event_type}</strong>
                is tomorrow. Here's everything you need for a smooth evening.
              </p>
            </td>
          </tr>

          <!-- Booking card -->
          {_booking_card(date_str, time_str, rooms_str, guest_count, arrival_time)}

          <!-- House rules -->
          <tr>
            <td style="padding:0 44px 36px;">
              {_label("Before you arrive")}
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                {_bullet("Sauvage is a shared community space. Ikinari Coffee, the Gallery, Fento kitchen, and Selection Sauvage wines may all be operating. Please stay within your booked areas.")}
                {_bullet(f"Leave every space exactly as you found it. The closing checklist takes around 15 minutes — please run through it before you leave.")}
                {_bullet(f"Music off and all guests out by <strong style='color:{C_INK};'>{end_time or 'your agreed end time'}</strong>.")}
                {_bullet(f'Your booking is governed by our <a href="{TERMS_URL}" style="color:{C_INK};font-weight:600;">Terms &amp; Conditions</a>. Please make sure your guests are aware.')}
              </table>
            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td style="padding:0 44px;">
              <hr style="border:none;border-top:1px solid rgba(26,26,24,0.08);margin:0 0 32px;">
            </td>
          </tr>

          <!-- Host -->
          <tr>
            <td style="padding:0 44px 44px;">
              {_label("Your host tomorrow")}
              <p style="margin:0 0 20px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:14px;line-height:1.75;color:{C_MUTED};">
                <strong style="color:{C_INK};">{host['name']}</strong> will be on hand for anything
                you need. Reach them directly on WhatsApp — for last-minute questions,
                access, or anything else on the day.
              </p>
              {_cta_button(f"WhatsApp {host['name']}", wa_link)}
              <p style="margin:12px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:11px;color:{C_MUTED};letter-spacing:0.04em;">{host['display']}</p>
            </td>
          </tr>"""

    html = _shell(rows, preheader=f"Your {event_type} is tomorrow — here's everything you need.")

    plain = f"""Hi {first},

Your {event_type} at Sauvage is tomorrow. Here's everything you need.

BOOKING DETAILS
Date:   {date_str}
Time:   {time_str}
Space:  {rooms_str}
Guests: {guest_count}
{"Setup arrival: " + arrival_time if arrival_time else ""}

BEFORE YOU ARRIVE
- Sauvage is a shared space. Stay within your booked areas.
- Leave every space as you found it. Closing checklist takes ~15 mins.
- Music off and guests out by {end_time or "your agreed end time"}.
- Full Terms & Conditions: {TERMS_URL}

YOUR HOST TOMORROW
{host['name']} is your point of contact.
WhatsApp: https://wa.me/{host['whatsapp']}  |  {host['display']}

See you tomorrow,
Sauvage Space · sauvage.amsterdam
"""
    return _send(client_email, subject, html, plain)


# ─────────────────────────────────────────────────────────────────────────────
# ② DAY OF
# ─────────────────────────────────────────────────────────────────────────────

def send_day_of(state: dict) -> bool:
    client_name  = state.get("client_name", "there")
    client_email = state.get("email", "")
    event_type   = state.get("event_type", "event")
    date_str     = _fmt_date(state.get("dates"))
    start_time   = state.get("start_time", "")
    end_time     = state.get("end_time", "")
    rooms_str    = _fmt_rooms(state.get("rooms"))
    guest_count  = state.get("guest_count", "")
    attributed   = state.get("attributed_host", "")
    arrival_time = state.get("arrival_time", "")

    if not client_email:
        return False

    host     = _host_info(attributed)
    time_str = f"{start_time} to {end_time}" if start_time and end_time else start_time or "see booking"
    wa_link  = f"https://wa.me/{host['whatsapp']}"
    first    = client_name.split()[0]
    subject  = f"Today at Sauvage — your {event_type} starts at {start_time}"

    rows = f"""
          <!-- Intro -->
          <tr>
            <td style="padding:44px 44px 8px;">
              {_label("Today")}
              {_h1("It's happening.")}
              <p style="margin:20px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:15px;line-height:1.75;color:{C_MUTED};">
                Hi {first} — your <strong style="color:{C_INK};">{event_type}</strong>
                is today. Doors open at
                <strong style="color:{C_INK};">{start_time or "your booked time"}</strong>.
                We hope it goes beautifully.
              </p>
            </td>
          </tr>

          <!-- Booking card -->
          {_booking_card(date_str, time_str, rooms_str, guest_count, arrival_time)}

          <!-- Quick reminders -->
          <tr>
            <td style="padding:0 44px 36px;">
              {_label("Quick reminders")}
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                {_bullet("Stay within your booked spaces and treat shared areas with care.")}
                {_bullet("Run through the closing checklist before you leave — it takes about 15 minutes.")}
                {_bullet(f"End time is <strong style='color:{C_INK};'>{end_time or 'as agreed'}</strong>. Music off, all guests out.")}
              </table>
            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td style="padding:0 44px;">
              <hr style="border:none;border-top:1px solid rgba(26,26,24,0.08);margin:0 0 32px;">
            </td>
          </tr>

          <!-- Host -->
          <tr>
            <td style="padding:0 44px 36px;">
              {_label("Need anything today?")}
              <p style="margin:0 0 20px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:14px;line-height:1.75;color:{C_MUTED};">
                <strong style="color:{C_INK};">{host['name']}</strong> is your host today.
                Message them on WhatsApp for access, questions, or anything that comes up.
              </p>
              {_cta_button(f"WhatsApp {host['name']}", wa_link)}
              <p style="margin:12px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:11px;color:{C_MUTED};letter-spacing:0.04em;">{host['display']}</p>
            </td>
          </tr>

          <!-- Sign-off -->
          <tr>
            <td style="padding:0 44px 44px;">
              <p style="margin:0;font-family:Georgia,'Times New Roman',serif;
                         font-size:16px;font-weight:300;font-style:italic;
                         color:{C_INK};line-height:1.6;">
                Enjoy every moment of it.
              </p>
            </td>
          </tr>"""

    html = _shell(rows, preheader=f"Today's the day — your {event_type} starts at {start_time}.")

    plain = f"""Hi {first},

Your {event_type} at Sauvage is today. Doors open at {start_time or "your booked time"}.

TODAY'S BOOKING
Time:   {time_str}
Space:  {rooms_str}
{"Setup arrival: " + arrival_time if arrival_time else ""}

QUICK REMINDERS
- Stay within your booked spaces.
- Close down checklist before you leave (~15 mins).
- End time: {end_time or "as agreed"} — music off, guests out.

NEED ANYTHING?
{host['name']} is your host today.
WhatsApp: https://wa.me/{host['whatsapp']}  |  {host['display']}

Enjoy every moment of it.

Sauvage Space · sauvage.amsterdam
"""
    return _send(client_email, subject, html, plain)


# ─────────────────────────────────────────────────────────────────────────────
# ③ DAY AFTER — Feedback
# ─────────────────────────────────────────────────────────────────────────────

def send_day_after(state: dict) -> bool:
    """
    Feedback email — best-practice format:
    - Warm, personal tone; reference their specific event
    - NPS-style overall rating (1–10) for quantitative tracking
    - One highlight question (positive reinforcement)
    - One improvement question (actionable insight)
    - Simple reply mechanism — no external form, low friction
    - Signed off by the attributed host to feel personal
    """
    client_name  = state.get("client_name", "there")
    client_email = state.get("email", "")
    event_type   = state.get("event_type", "event")
    attributed   = state.get("attributed_host", "")

    if not client_email:
        return False

    host    = _host_info(attributed)
    first   = client_name.split()[0]
    subject = f"How was your {event_type}? — Sauvage"

    rows = f"""
          <!-- Intro -->
          <tr>
            <td style="padding:44px 44px 8px;">
              {_label("We'd love to hear from you")}
              {_h1("How did it go?")}
              <p style="margin:20px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:15px;line-height:1.75;color:{C_MUTED};">
                Hi {first} — thank you for hosting your <strong style="color:{C_INK};">{event_type}</strong>
                at Sauvage. We hope it was everything you wanted it to be.
              </p>
              <p style="margin:14px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:14px;line-height:1.75;color:{C_MUTED};">
                We read every reply personally. Three short questions — two minutes at most.
                Your answers shape how we improve the space for everyone.
              </p>
            </td>
          </tr>

          <!-- Q1 -->
          <tr>
            <td style="padding:32px 44px 0;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:{C_GOLD};border-radius:2px;
                            border:1px solid rgba(26,26,24,0.08);">
                <tr>
                  <td style="padding:24px 28px;">
                    <p style="margin:0 0 4px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                               font-size:9px;letter-spacing:0.2em;text-transform:uppercase;
                               color:{C_WARM};">01 &mdash; Overall</p>
                    <p style="margin:0 0 10px;font-family:Georgia,serif;font-size:17px;
                               font-weight:400;color:{C_INK};line-height:1.4;">
                      On a scale of 1&ndash;10, how would you rate your overall experience at Sauvage?
                    </p>
                    <p style="margin:0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                               font-size:12px;color:{C_MUTED};line-height:1.6;">
                      1 = not what we hoped, 10 = couldn't have been better.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Q2 -->
          <tr>
            <td style="padding:12px 44px 0;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:{C_GOLD};border-radius:2px;
                            border:1px solid rgba(26,26,24,0.08);">
                <tr>
                  <td style="padding:24px 28px;">
                    <p style="margin:0 0 4px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                               font-size:9px;letter-spacing:0.2em;text-transform:uppercase;
                               color:{C_WARM};">02 &mdash; Highlight</p>
                    <p style="margin:0 0 10px;font-family:Georgia,serif;font-size:17px;
                               font-weight:400;color:{C_INK};line-height:1.4;">
                      What was the highlight of the event — something we got right?
                    </p>
                    <p style="margin:0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                               font-size:12px;color:{C_MUTED};line-height:1.6;">
                      Could be the space, the booking process, your host, the add-ons — anything.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Q3 -->
          <tr>
            <td style="padding:12px 44px 0;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:{C_GOLD};border-radius:2px;
                            border:1px solid rgba(26,26,24,0.08);">
                <tr>
                  <td style="padding:24px 28px;">
                    <p style="margin:0 0 4px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                               font-size:9px;letter-spacing:0.2em;text-transform:uppercase;
                               color:{C_WARM};">03 &mdash; Improve</p>
                    <p style="margin:0 0 10px;font-family:Georgia,serif;font-size:17px;
                               font-weight:400;color:{C_INK};line-height:1.4;">
                      Is there anything we could have done better or made easier?
                    </p>
                    <p style="margin:0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                               font-size:12px;color:{C_MUTED};line-height:1.6;">
                      No detail too small — this is exactly what helps us improve.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- CTA -->
          <tr>
            <td style="padding:32px 44px 16px;">
              {_cta_button("Reply with your feedback", f"mailto:{FROM_EMAIL}?subject=Feedback%20%E2%80%94%20{first}")}
              <p style="margin:14px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:12px;color:{C_MUTED};line-height:1.6;">
                Or just reply to this email — it goes straight to {host['name']}.
              </p>
            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td style="padding:8px 44px 0;">
              <hr style="border:none;border-top:1px solid rgba(26,26,24,0.08);margin:0 0 32px;">
            </td>
          </tr>

          <!-- Sign-off -->
          <tr>
            <td style="padding:0 44px 44px;">
              <p style="margin:0 0 6px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:14px;line-height:1.75;color:{C_MUTED};">
                Thank you again, {first}. We'd love to have you back.
              </p>
              <p style="margin:0;font-family:Georgia,serif;font-size:15px;
                         font-style:italic;font-weight:300;color:{C_INK};">
                {host['name']} &amp; the Sauvage team
              </p>
            </td>
          </tr>"""

    html = _shell(rows, preheader=f"Two minutes — how did your {event_type} go? We read every reply.")

    plain = f"""Hi {first},

Thank you for hosting your {event_type} at Sauvage. We hope it was everything you wanted.

We read every reply personally — three short questions, two minutes at most.

01 — OVERALL
On a scale of 1-10, how would you rate your overall experience at Sauvage?
(1 = not what we hoped, 10 = couldn't have been better)

02 — HIGHLIGHT
What was the highlight of the event — something we got right?

03 — IMPROVE
Is there anything we could have done better or made easier?

Just hit reply — it goes straight to {host['name']}.

Thank you again. We'd love to have you back.

{host['name']} & the Sauvage team
sauvage.amsterdam
"""
    return _send(client_email, subject, html, plain)
