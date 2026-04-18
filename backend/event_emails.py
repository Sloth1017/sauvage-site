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
from calendar_links import google_calendar_url, ics_download_url

# ── SMTP config ───────────────────────────────────────────────────────────────
SMTP_SERVER   = os.getenv("SMTP_SERVER",   "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER",     "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL    = os.getenv("FROM_EMAIL",    "bookings@sauvage.amsterdam")
BASE_URL      = os.getenv("BASE_URL",      "https://sauvage.amsterdam")

# ── Brand tokens (matches sauvage.amsterdam CSS variables) ────────────────────
C_INK    = "#1a1a18"
C_CREAM  = "#f7f4ef"
C_GOLD   = "#F5F1E6"   # card backgrounds — the site's "--gold"
C_WARM   = "#8b6f47"   # accent colour — the site's "--warm"
C_MUTED  = "#6b6560"
C_BORDER = "rgba(26,26,24,0.10)"
C_WHITE  = "#ffffff"

LOGO_URL  = f"{BASE_URL}/media/sauvage-logo.png"
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
    from datetime import datetime as _dt
    raw = dates[0] if isinstance(dates, list) else str(dates or "")
    try:
        return _dt.strptime(raw.strip(), "%Y-%m-%d").strftime("%A %-d %B %Y")
    except ValueError:
        return raw


# ── Shared shell ──────────────────────────────────────────────────────────────

def _shell(body_rows: str, preheader: str = "", pixel_url: str = "") -> str:
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
        <td style="background:{C_INK};padding:16px 44px 14px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <!-- Logo mark -->
              <td style="vertical-align:middle;">
                <img src="{LOGO_URL}" alt="Sauvage" width="120" height="120"
                     style="display:block;border:0;" />
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
{f'<img src="{pixel_url}" width="1" height="1" border="0" style="display:block;width:1px;height:1px;" alt="">' if pixel_url else ""}
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


def _wine_section(booking_id: str = "", client_name: str = "",
                  client_email: str = "", event_type: str = "",
                  ref: str = "") -> str:
    from urllib.parse import urlencode
    params = urlencode({
        "booking": booking_id,
        "name":    client_name,
        "email":   client_email,
        "event":   event_type,
        "ref":     ref,
    })
    wine_url = f"{BASE_URL}/wines?{params}"
    return f"""
          <tr>
            <td style="padding:0 44px 36px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="border:1px solid rgba(26,26,24,0.1);border-radius:2px;">
                <tr>
                  <td style="padding:22px 28px;">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td style="vertical-align:middle;">
                          <p style="margin:0 0 4px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:9px;letter-spacing:0.2em;text-transform:uppercase;
                                     color:{C_WARM};">Selection Sauvage</p>
                          <p style="margin:0;font-family:Georgia,serif;font-size:16px;
                                     font-weight:300;color:{C_INK};line-height:1.4;">
                            Pre-order natural wines for your event</p>
                          <p style="margin:5px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:12px;color:{C_MUTED};line-height:1.6;">
                            Use code <strong style="color:{C_INK};">IN-HOUSE</strong> at checkout</p>
                        </td>
                        <td align="right" style="vertical-align:middle;padding-left:20px;white-space:nowrap;">
                          <a href="{wine_url}"
                             style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                    font-size:10px;font-weight:700;letter-spacing:0.18em;
                                    text-transform:uppercase;color:{C_INK};text-decoration:none;
                                    display:inline-block;border-bottom:2px solid {C_WARM};
                                    padding-bottom:2px;">Order wines &rarr;</a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def _calendar_widget(title: str, date_str: str, start_time: str,
                     end_time: str, description: str = "") -> str:
    gcal = google_calendar_url(title, date_str, start_time, end_time, description)
    ical = ics_download_url(BASE_URL, title, date_str, start_time, end_time, description)
    if not gcal or not ical:
        return ""
    gcal_icon = f"{BASE_URL}/media/icon-google-calendar.png"
    ical_icon = f"{BASE_URL}/media/icon-apple-calendar.png"
    return (
        f'<p style="margin:10px 0 0;font-size:0;line-height:0;">'
        f'<a href="{gcal}" style="display:inline-block;vertical-align:middle;margin-right:8px;text-decoration:none;">'
        f'<img src="{gcal_icon}" alt="Add to Google Calendar" width="32" height="32"'
        f' style="display:inline-block;border:0;border-radius:6px;vertical-align:middle;"></a>'
        f'<a href="{ical}" style="display:inline-block;vertical-align:middle;text-decoration:none;">'
        f'<img src="{ical_icon}" alt="Add to Apple Calendar" width="26" height="26"'
        f' style="display:inline-block;border:0;border-radius:5px;vertical-align:middle;"></a>'
        f'</p>'
    )


def _booking_card(date_str, time_str, rooms_str, guest_count, arrival_time="", cal_widget="") -> str:
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
                          {cal_widget}
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
                      <tr>
                        <td colspan="2" style="padding:14px 0 0;vertical-align:top;
                                               border-top:1px solid rgba(26,26,24,0.08);">
                          <p style="margin:0 0 3px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:9px;letter-spacing:0.16em;text-transform:uppercase;color:{C_MUTED};">Location</p>
                          <a href="https://maps.app.goo.gl/V43TU8mohCjaNLKeA"
                             style="font-family:Georgia,serif;font-size:15px;font-weight:400;
                                    color:{C_INK};text-decoration:underline;">
                            Potgieterstraat 47H, Amsterdam
                          </a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def _wifi_card() -> str:
    return f"""
          <tr>
            <td style="padding:0 44px 32px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:{C_GOLD};border-radius:2px;
                            border:1px solid rgba(26,26,24,0.08);">
                <tr>
                  <td style="padding:22px 28px;">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td>
                          <p style="margin:0 0 14px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:9px;letter-spacing:0.2em;text-transform:uppercase;
                                     color:{C_WARM};">Wi-Fi</p>
                        </td>
                      </tr>
                      <tr>
                        <td width="50%" style="vertical-align:top;">
                          <p style="margin:0 0 3px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:9px;letter-spacing:0.14em;text-transform:uppercase;
                                     color:{C_MUTED};">Network</p>
                          <p style="margin:0;font-family:Georgia,serif;font-size:17px;
                                     font-weight:400;font-style:italic;color:{C_INK};
                                     letter-spacing:0.04em;">@Sauvage</p>
                        </td>
                        <td width="50%" style="vertical-align:top;">
                          <p style="margin:0 0 3px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:9px;letter-spacing:0.14em;text-transform:uppercase;
                                     color:{C_MUTED};">Password</p>
                          <p style="margin:0;font-size:0;line-height:0;">
                            <span style="font-family:Georgia,serif;font-size:17px;
                                         font-weight:400;font-style:italic;color:{C_INK};
                                         letter-spacing:0.04em;vertical-align:middle;">natural1</span>
                            <a href="{BASE_URL}/copy?text=natural1"
                               style="display:inline-block;vertical-align:middle;margin-left:8px;
                                      text-decoration:none;opacity:0.45;">
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                                   xmlns="http://www.w3.org/2000/svg"
                                   style="display:inline-block;vertical-align:middle;">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"
                                      stroke="#1a1a18" stroke-width="2" fill="none"/>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                                      stroke="#1a1a18" stroke-width="2" fill="none"/>
                              </svg>
                            </a>
                          </p>
                        </td>
                      </tr>
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


def _whatsapp_button(name: str, href: str) -> str:
    return (
        f'<a href="{href}" '
        f'style="display:inline-block;background:#25D366;color:#1a1a18;'
        f'text-decoration:none;padding:13px 28px;border-radius:50px;'
        f'font-family:\'Helvetica Neue\',Helvetica,Arial,sans-serif;'
        f'font-size:13px;font-weight:600;letter-spacing:0.01em;">'
        f'WhatsApp {name} &nbsp;&#8599;</a>'
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
    booking_id   = state.get("booking_id", "")

    if not client_email:
        return False

    host     = _host_info(attributed)
    time_str = f"{start_time} to {end_time}" if start_time and end_time else start_time or "see booking"
    wa_link  = f"https://wa.me/{host['whatsapp']}"
    first    = client_name.split()[0]
    subject  = f"Your {event_type} at Sauvage - Tomorrow"
    cal_widget = _calendar_widget(
        f"{event_type} at Sauvage", date_str, start_time, end_time,
        f"Sauvage Space · Potgieterstraat 47H, Amsterdam"
    )

    rows = f"""
          <!-- Intro -->
          <tr>
            <td style="padding:44px 44px 8px;">
              {_label("Reminder")}
              {_h1(f"Tomorrow at Sauvage")}
              <p style="margin:20px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:15px;line-height:1.75;color:{C_MUTED};">
                Hi {first}, your <strong style="color:{C_INK};">{event_type}</strong>
                is tomorrow. Here's everything you need for a smooth evening.
              </p>
            </td>
          </tr>

          <!-- Booking card -->
          {_booking_card(date_str, time_str, rooms_str, guest_count, arrival_time, cal_widget)}

          <!-- Wi-Fi -->
          {_wifi_card()}

          <!-- House rules -->
          <tr>
            <td style="padding:0 44px 36px;">
              {_label("Before you arrive")}
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                {_bullet("Sauvage is a shared community space. Ikinari Coffee, the Gallery, Fento kitchen, and Selection Sauvage wines may all be operating. Please stay within your booked areas.")}
                {_bullet(f"Leave every space exactly as you found it. The closing checklist takes around 15 minutes, please run through it before you leave.")}
                {_bullet(f"Music off and all guests out by <strong style='color:{C_INK};'>{end_time or 'your agreed end time'}</strong>.")}
                {_bullet(f'Your booking is governed by our <a href="{TERMS_URL}" style="color:{C_INK};font-weight:600;">Terms &amp; Conditions</a>. Please make sure your guests are aware.')}
              </table>
            </td>
          </tr>

          <!-- Wine -->
          {_wine_section(booking_id, client_name, client_email, event_type, "day-before")}

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
                you need. Reach them directly on WhatsApp for last-minute questions,
                access, or anything else on the day.
              </p>
              {_whatsapp_button(host['name'], wa_link)}
              <p style="margin:12px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:11px;color:{C_MUTED};letter-spacing:0.04em;">{host['display']}</p>
            </td>
          </tr>"""

    pixel = f"{BASE_URL}/track/open?rid={booking_id}&type=day-before" if booking_id else ""
    html = _shell(rows, preheader=f"Your {event_type} is tomorrow. Here's everything you need.", pixel_url=pixel)

    plain = f"""Hi {first},

Your {event_type} at Sauvage is tomorrow. Here's everything you need.

BOOKING DETAILS
Date:     {date_str}
Time:     {time_str}
Space:    {rooms_str}
Guests:   {guest_count}
{"Setup arrival: " + arrival_time if arrival_time else ""}
Location: Potgieterstraat 47H, Amsterdam
Maps:     https://maps.app.goo.gl/V43TU8mohCjaNLKeA

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
    booking_id   = state.get("booking_id", "")

    if not client_email:
        return False

    host     = _host_info(attributed)
    time_str = f"{start_time} to {end_time}" if start_time and end_time else start_time or "see booking"
    wa_link  = f"https://wa.me/{host['whatsapp']}"
    first    = client_name.split()[0]
    subject  = f"Today at Sauvage - your {event_type} starts at {start_time}"
    cal_widget = _calendar_widget(
        f"{event_type} at Sauvage", date_str, start_time, end_time,
        f"Sauvage Space · Potgieterstraat 47H, Amsterdam"
    )

    rows = f"""
          <!-- Intro -->
          <tr>
            <td style="padding:44px 44px 8px;">
              {_label("Today")}
              {_h1("It's happening.")}
              <p style="margin:20px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:15px;line-height:1.75;color:{C_MUTED};">
                Hi {first}, your <strong style="color:{C_INK};">{event_type}</strong>
                is today. Doors open at
                <strong style="color:{C_INK};">{start_time or "your booked time"}</strong>.
                We hope it goes beautifully.
              </p>
            </td>
          </tr>

          <!-- Booking card -->
          {_booking_card(date_str, time_str, rooms_str, guest_count, arrival_time, cal_widget)}

          <!-- Wi-Fi -->
          {_wifi_card()}

          <!-- Quick reminders -->
          <tr>
            <td style="padding:0 44px 36px;">
              {_label("Quick reminders")}
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                {_bullet("Stay within your booked spaces and treat shared areas with care.")}
                {_bullet("Run through the closing checklist before you leave, it takes about 15 minutes.")}
                {_bullet(f"End time is <strong style='color:{C_INK};'>{end_time or 'as agreed'}</strong>. Music off, all guests out.")}
              </table>
            </td>
          </tr>

          <!-- Wine -->
          {_wine_section(booking_id, client_name, client_email, event_type, "day-of")}

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
              {_whatsapp_button(host['name'], wa_link)}
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

    pixel = f"{BASE_URL}/track/open?rid={booking_id}&type=day-of" if booking_id else ""
    html = _shell(rows, preheader=f"Today's the day. Your {event_type} starts at {start_time}.", pixel_url=pixel)

    plain = f"""Hi {first},

Your {event_type} at Sauvage is today. Doors open at {start_time or "your booked time"}.

TODAY'S BOOKING
Time:     {time_str}
Space:    {rooms_str}
{"Setup arrival: " + arrival_time if arrival_time else ""}
Location: Potgieterstraat 47H, Amsterdam
Maps:     https://maps.app.goo.gl/V43TU8mohCjaNLKeA

QUICK REMINDERS
- Stay within your booked spaces.
- Close down checklist before you leave (~15 mins).
- End time: {end_time or "as agreed"}, music off, guests out.

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
    booking_id   = state.get("booking_id", "")

    if not client_email:
        return False

    host    = _host_info(attributed)
    first   = client_name.split()[0]
    subject = f"How was your {event_type}? Sauvage"

    # Rating buttons 1–10
    rating_cells = ""
    for n in range(1, 11):
        subj = f"Rating%3A%20{n}%2F10%20%7C%20{first}"
        body = f"My%20overall%20rating%3A%20{n}%2F10%0A%0A"
        href = f"mailto:{FROM_EMAIL}?subject={subj}&body={body}"
        rating_cells += (
            f'<td style="padding:0 4px 0 0;">'
            f'<a href="{href}" style="display:inline-block;width:34px;height:34px;'
            f'line-height:34px;text-align:center;background:{C_INK};border-radius:2px;'
            f'font-family:\'Helvetica Neue\',Helvetica,Arial,sans-serif;font-size:12px;'
            f'font-weight:600;color:{C_WHITE};text-decoration:none;">{n}</a>'
            f'</td>'
        )

    feedback_url = f"{BASE_URL}/feedback"
    mailto_fallback = f"mailto:{FROM_EMAIL}?subject=Feedback%20%7C%20{first}"

    rows = f"""
          <!-- Intro -->
          <tr>
            <td style="padding:44px 44px 8px;">
              {_label("We'd love to hear from you")}
              {_h1("How did it go?")}
              <p style="margin:20px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:15px;line-height:1.75;color:{C_MUTED};">
                Hi {first}, thank you for hosting your <strong style="color:{C_INK};">{event_type}</strong>
                at Sauvage. We hope it was everything you wanted it to be.
              </p>
              <p style="margin:14px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:14px;line-height:1.75;color:{C_MUTED};">
                We read every response personally. Three short questions, two minutes at most.
              </p>
            </td>
          </tr>

          <!-- Feedback form -->
          <tr>
            <td style="padding:28px 44px 0;">
              <form action="{feedback_url}" method="POST"
                    style="margin:0;">
                <input type="hidden" name="name"    value="{client_name}">
                <input type="hidden" name="event"   value="{event_type}">
                <input type="hidden" name="booking" value="{booking_id}">

                <!-- Q1: Rating -->
                <table width="100%" cellpadding="0" cellspacing="0" border="0"
                       style="background:{C_GOLD};border-radius:2px;
                              border:1px solid rgba(26,26,24,0.08);margin-bottom:10px;">
                  <tr>
                    <td style="padding:22px 28px;">
                      <p style="margin:0 0 4px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                 font-size:9px;letter-spacing:0.2em;text-transform:uppercase;
                                 color:{C_WARM};">01. Overall</p>
                      <p style="margin:0 0 16px;font-family:Georgia,serif;font-size:16px;
                                 font-weight:400;color:{C_INK};line-height:1.4;">
                        How would you rate your overall experience?
                      </p>
                      <!-- Clickable mailto buttons (universal fallback) -->
                      <table cellpadding="0" cellspacing="0" border="0" style="margin-bottom:10px;">
                        <tr>{rating_cells}</tr>
                      </table>
                      <p style="margin:4px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                 font-size:10px;color:{C_MUTED};">1 = not what we hoped &nbsp; 10 = couldn't have been better</p>
                      <!-- Hidden radio inputs for form submission -->
                      <div style="display:none;">
                        {"".join(f'<input type="radio" name="rating" value="{n}">' for n in range(1,11))}
                      </div>
                    </td>
                  </tr>
                </table>

                <!-- Q2: Highlight -->
                <table width="100%" cellpadding="0" cellspacing="0" border="0"
                       style="background:{C_GOLD};border-radius:2px;
                              border:1px solid rgba(26,26,24,0.08);margin-bottom:10px;">
                  <tr>
                    <td style="padding:22px 28px;">
                      <p style="margin:0 0 4px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                 font-size:9px;letter-spacing:0.2em;text-transform:uppercase;
                                 color:{C_WARM};">02. Highlight</p>
                      <p style="margin:0 0 12px;font-family:Georgia,serif;font-size:16px;
                                 font-weight:400;color:{C_INK};line-height:1.4;">
                        What was the highlight of the event?
                      </p>
                      <textarea name="highlight" rows="3" placeholder="The space, the host, the add-ons..."
                                style="width:100%;box-sizing:border-box;padding:12px 14px;
                                       font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                       font-size:13px;color:{C_INK};background:{C_WHITE};
                                       border:1px solid rgba(26,26,24,0.15);border-radius:2px;
                                       resize:vertical;outline:none;"></textarea>
                    </td>
                  </tr>
                </table>

                <!-- Q3: Improve -->
                <table width="100%" cellpadding="0" cellspacing="0" border="0"
                       style="background:{C_GOLD};border-radius:2px;
                              border:1px solid rgba(26,26,24,0.08);margin-bottom:10px;">
                  <tr>
                    <td style="padding:22px 28px;">
                      <p style="margin:0 0 4px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                 font-size:9px;letter-spacing:0.2em;text-transform:uppercase;
                                 color:{C_WARM};">03. Improve</p>
                      <p style="margin:0 0 12px;font-family:Georgia,serif;font-size:16px;
                                 font-weight:400;color:{C_INK};line-height:1.4;">
                        Anything we could have done better?
                      </p>
                      <textarea name="improve" rows="3" placeholder="No detail too small..."
                                style="width:100%;box-sizing:border-box;padding:12px 14px;
                                       font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                       font-size:13px;color:{C_INK};background:{C_WHITE};
                                       border:1px solid rgba(26,26,24,0.15);border-radius:2px;
                                       resize:vertical;outline:none;"></textarea>
                    </td>
                  </tr>
                </table>

                <!-- General comment -->
                <table width="100%" cellpadding="0" cellspacing="0" border="0"
                       style="background:{C_GOLD};border-radius:2px;
                              border:1px solid rgba(26,26,24,0.08);margin-bottom:24px;">
                  <tr>
                    <td style="padding:22px 28px;">
                      <p style="margin:0 0 4px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                 font-size:9px;letter-spacing:0.2em;text-transform:uppercase;
                                 color:{C_WARM};">Anything else</p>
                      <p style="margin:0 0 12px;font-family:Georgia,serif;font-size:16px;
                                 font-weight:400;color:{C_INK};line-height:1.4;">
                        Any other thoughts or comments?
                      </p>
                      <textarea name="comment" rows="4" placeholder="Anything at all..."
                                style="width:100%;box-sizing:border-box;padding:12px 14px;
                                       font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                       font-size:13px;color:{C_INK};background:{C_WHITE};
                                       border:1px solid rgba(26,26,24,0.15);border-radius:2px;
                                       resize:vertical;outline:none;"></textarea>
                    </td>
                  </tr>
                </table>

                <!-- Submit -->
                <button type="submit"
                        style="display:inline-block;background:{C_INK};color:{C_WHITE};
                               border:none;cursor:pointer;padding:14px 36px;border-radius:1px;
                               font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                               font-size:10px;font-weight:600;letter-spacing:0.18em;
                               text-transform:uppercase;">Send Feedback</button>

              </form>

              <!-- Fallback for clients that strip forms -->
              <p style="margin:20px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:11px;color:{C_MUTED};line-height:1.7;">
                Form not showing?
                <a href="{mailto_fallback}" style="color:{C_INK};font-weight:600;">Reply by email</a>
                — it goes straight to {host['name']}.
              </p>
            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td style="padding:32px 44px 0;">
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

    pixel = f"{BASE_URL}/track/open?rid={booking_id}&type=day-after" if booking_id else ""
    html = _shell(rows, preheader=f"Two minutes. How did your {event_type} go? We read every reply.", pixel_url=pixel)

    plain = f"""Hi {first},

Thank you for hosting your {event_type} at Sauvage. We hope it was everything you wanted.

We read every reply personally. Three short questions, two minutes at most.

01. OVERALL
On a scale of 1-10, how would you rate your overall experience at Sauvage?
(1 = not what we hoped, 10 = couldn't have been better)

02. HIGHLIGHT
What was the highlight of the event, something we got right?

03. IMPROVE
Is there anything we could have done better or made easier?

Just hit reply, it goes straight to {host['name']}.

Thank you again. We'd love to have you back.

{host['name']} & the Sauvage team
sauvage.amsterdam
"""
    return _send(client_email, subject, html, plain)
