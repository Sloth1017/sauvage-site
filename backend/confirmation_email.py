"""
confirmation_email.py
---------------------
Sends the booking confirmation email to the client on payment.

Includes:
  - Welcome message
  - Full booking summary
  - Community-space etiquette reminder
  - Website link
  - Arrival time request (form link → updates Airtable on submit)

Arrival form security: HMAC-SHA256(record_id, ARRIVAL_SECRET) so only
the legitimate client link can write to their Airtable record.
"""

import os
import hmac
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from calendar_links import google_calendar_url, ics_download_url

# ── Config ────────────────────────────────────────────────────────────────────
SMTP_SERVER   = os.getenv("SMTP_SERVER",   "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER",     "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL    = os.getenv("FROM_EMAIL",    "bookings@sauvage.amsterdam")
BASE_URL      = os.getenv("BASE_URL",      "https://sauvage.amsterdam")
ARRIVAL_SECRET = os.getenv("ARRIVAL_SECRET", "sauvage-arrival-secret-change-me")


# ── Token helpers ─────────────────────────────────────────────────────────────

def generate_arrival_token(record_id: str) -> str:
    """HMAC-SHA256 token that authorises writing arrival time for one record."""
    return hmac.new(
        ARRIVAL_SECRET.encode(),
        record_id.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def verify_arrival_token(record_id: str, token: str) -> bool:
    expected = generate_arrival_token(record_id)
    return hmac.compare_digest(expected, token)


# ── Email ─────────────────────────────────────────────────────────────────────

def _fmt_rooms(rooms) -> str:
    if isinstance(rooms, list):
        return ", ".join(rooms)
    return str(rooms or "TBC")

def _fmt_date(dates) -> str:
    from datetime import datetime as _dt
    raw = dates[0] if isinstance(dates, list) else str(dates or "TBC")
    try:
        return _dt.strptime(raw.strip(), "%Y-%m-%d").strftime("%A %-d %B %Y")
    except ValueError:
        return raw


def send_booking_confirmation(
    record_id: str,
    state: dict,
    invoice_pdf: bytes = None,
    invoice_number: str = "",
    invoice_url: str = "",
) -> bool:
    """
    Send the branded booking confirmation email to the client.
    Optionally attaches a PDF invoice.
    Returns True on success, False on failure.
    """
    client_email = state.get("email", "")
    if not client_email:
        print("[Email] No client email in state — skipping confirmation")
        return False

    if not SMTP_USER or not SMTP_PASSWORD:
        print("[Email] SMTP not configured — skipping confirmation email")
        return False

    client_name  = state.get("client_name", "there")
    event_type   = state.get("event_type",  "Event")
    date_str     = _fmt_date(state.get("dates"))
    start_time   = state.get("start_time",  "")
    end_time     = state.get("end_time",    "")
    rooms_str    = _fmt_rooms(state.get("rooms"))
    guest_count  = state.get("guest_count", "")
    quote_total  = state.get("quote_total", "")

    time_str = f"{start_time} to {end_time}" if start_time and end_time else start_time or "TBC"
    deposit  = "€300" if "kitchen" in rooms_str.lower() else "€50"

    from urllib.parse import urlencode as _ue
    wine_params = _ue({"booking": record_id, "name": client_name,
                       "email": client_email, "event": event_type, "ref": "confirmation"})
    wine_url = f"{BASE_URL}/wines?{wine_params}"

    gcal_url = google_calendar_url(
        f"{event_type} at Sauvage", date_str, start_time, end_time,
        "Sauvage Space · Potgieterstraat 47H, Amsterdam"
    )
    ical_url = ics_download_url(
        BASE_URL, f"{event_type} at Sauvage", date_str, start_time, end_time,
        "Sauvage Space · Potgieterstraat 47H, Amsterdam"
    )
    gcal_icon = f"{BASE_URL}/media/icon-google-calendar.png"
    ical_icon = f"{BASE_URL}/media/icon-apple-calendar.png"
    cal_widget = (
        f'<p style="margin:8px 0 0;font-size:0;line-height:0;">'
        f'<a href="{gcal_url}" style="display:inline-block;vertical-align:middle;margin-right:8px;text-decoration:none;">'
        f'<img src="{gcal_icon}" alt="Add to Google Calendar" width="32" height="32"'
        f' style="display:inline-block;border:0;border-radius:6px;vertical-align:middle;"></a>'
        f'<a href="{ical_url}" style="display:inline-block;vertical-align:middle;text-decoration:none;">'
        f'<img src="{ical_icon}" alt="Add to Apple Calendar" width="26" height="26"'
        f' style="display:inline-block;border:0;border-radius:5px;vertical-align:middle;"></a>'
        f'</p>'
    ) if gcal_url and ical_url else ""

    arrival_token = generate_arrival_token(record_id)
    arrival_url   = f"{BASE_URL}/arrival?record={record_id}&token={arrival_token}"

    # Invoice section (optional) — minimal, tertiary weight
    inv_html = ""
    if invoice_url:
        inv_html = f"""
          <!-- Invoice — tertiary, text-level only -->
          <tr>
            <td style="padding:0 40px 28px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="border-top:1px solid #e8e4de;">
                <tr>
                  <td style="padding:20px 0 0;">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td style="vertical-align:middle;">
                          <p style="margin:0;font-size:10px;letter-spacing:0.18em;
                                     text-transform:uppercase;color:#aaa;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
                            Invoice
                          </p>
                          <p style="margin:4px 0 0;font-size:13px;color:#555;
                                     font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
                            {invoice_number}
                          </p>
                        </td>
                        <td align="right" style="vertical-align:middle;">
                          <a href="{invoice_url}"
                             style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                    font-size:11px;letter-spacing:0.14em;text-transform:uppercase;
                                    color:#b8860b;text-decoration:none;font-weight:600;">
                            View &rarr;
                          </a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""
    inv_plain = (
        f"\nINVOICE\n{invoice_number}\nView: {invoice_url}\n"
        if invoice_url else ""
    )

    subject = f"Your Sauvage Space booking is confirmed"

    logo_url = f"{BASE_URL}/media/sauvage-logo.png"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Booking Confirmed - Sauvage Space</title>
</head>
<body style="margin:0;padding:0;background:#f5f3ef;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;color:#1a1a1a;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f5f3ef;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:4px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

          <!-- Header with logo -->
          <tr>
            <td style="background:#1a1a1a;padding:28px 40px 24px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="vertical-align:middle;">
                    <img src="{logo_url}" alt="Sauvage Space" width="72" height="72"
                         style="display:block;width:72px;height:72px;border:0;filter:invert(1);" />
                  </td>
                  <td style="vertical-align:middle;padding-left:20px;">
                    <p style="margin:0 0 4px;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#666;font-weight:500;">Potgieterstraat 47H, Amsterdam</p>
                    <h1 style="margin:0;font-size:24px;font-weight:400;color:#ffffff;letter-spacing:-0.2px;">Booking Confirmed</h1>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Gold accent line -->
          <tr>
            <td style="background:#b8860b;height:3px;font-size:0;line-height:0;">&nbsp;</td>
          </tr>

          <!-- Greeting -->
          <tr>
            <td style="padding:36px 40px 24px;">
              <p style="margin:0 0 16px;font-size:16px;line-height:1.6;color:#1a1a1a;">
                Hi {client_name},
              </p>
              <p style="margin:0;font-size:16px;line-height:1.6;color:#333;">
                Welcome to Sauvage. Your deposit is in and your booking is locked — we're looking forward to hosting you.
              </p>
            </td>
          </tr>

          <!-- Booking summary -->
          <tr>
            <td style="padding:0 40px 32px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f5f3ef;border-radius:4px;padding:24px;">
                <tr>
                  <td style="padding:0 24px;">
                    <p style="margin:0 0 4px;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#999;font-weight:600;">Your Event</p>
                    <p style="margin:0 0 20px;font-size:17px;font-weight:500;color:#1a1a1a;">{event_type}</p>

                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Date</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">{date_str}</p>
                          {cal_widget}
                        </td>
                        <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Time</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">{time_str}</p>
                        </td>
                      </tr>
                      <tr>
                        <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Space</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">{rooms_str}</p>
                        </td>
                        <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Guests</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">{guest_count}</p>
                        </td>
                      </tr>
                      {"" if not quote_total else f'''<tr>
                        <td width="50%" style="padding:0;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Total</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">&#8364;{quote_total} incl. VAT</p>
                        </td>
                        <td width="50%" style="padding:0;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#aaa;">Deposit Paid</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">{deposit}</p>
                        </td>
                      </tr>'''}
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ① ARRIVAL — dominant CTA -->
          <tr>
            <td style="padding:0 40px 12px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:#1a1a18;border-radius:2px;overflow:hidden;">
                <tr>
                  <td style="background:#b8860b;height:3px;font-size:0;line-height:0;"></td>
                </tr>
                <tr>
                  <td style="padding:32px 36px 36px;">
                    <p style="margin:0 0 8px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                               font-size:9px;letter-spacing:0.22em;text-transform:uppercase;color:#b8860b;">
                      One thing from you
                    </p>
                    <p style="margin:0 0 10px;font-family:Georgia,serif;font-size:22px;
                               font-weight:300;color:#ffffff;line-height:1.3;">
                      When are you planning to arrive?
                    </p>
                    <p style="margin:0 0 28px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                               font-size:13px;line-height:1.7;color:rgba(255,255,255,0.5);">
                      Let us know your setup arrival time so we can coordinate with the other residents.
                      Takes 10 seconds.
                    </p>
                    <a href="{arrival_url}"
                       style="display:block;background:#ffffff;color:#1a1a18;text-decoration:none;
                              padding:16px 0;border-radius:1px;text-align:center;
                              font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                              font-size:10px;font-weight:700;letter-spacing:0.22em;
                              text-transform:uppercase;">
                      Confirm arrival time
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ② WINES — secondary -->
          <tr>
            <td style="padding:12px 40px 12px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="border:1px solid #e8e4de;border-radius:2px;">
                <tr>
                  <td style="padding:24px 28px;">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td style="vertical-align:middle;">
                          <p style="margin:0 0 4px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:9px;letter-spacing:0.2em;text-transform:uppercase;color:#b8860b;">
                            Selection Sauvage
                          </p>
                          <p style="margin:0;font-family:Georgia,serif;font-size:16px;
                                     font-weight:300;color:#1a1a18;line-height:1.4;">
                            Pre-order natural wines for your event
                          </p>
                          <p style="margin:6px 0 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                     font-size:12px;color:#888;line-height:1.6;">
                            Use code <strong style="color:#555;">IN-HOUSE</strong> at checkout
                          </p>
                        </td>
                        <td align="right" style="vertical-align:middle;padding-left:20px;white-space:nowrap;">
                          <a href="{wine_url}"
                             style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                                    font-size:10px;font-weight:700;letter-spacing:0.18em;
                                    text-transform:uppercase;color:#1a1a18;text-decoration:none;
                                    display:inline-block;border-bottom:2px solid #b8860b;
                                    padding-bottom:2px;">
                            Order wines &rarr;
                          </a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Community space note -->
          <tr>
            <td style="padding:24px 40px 0px;">
              <p style="margin:0 0 6px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:9px;letter-spacing:0.18em;text-transform:uppercase;color:#aaa;">
                A shared space
              </p>
              <p style="margin:0 0 10px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                         font-size:13px;line-height:1.75;color:#666;">
                Sauvage is home to several independent businesses. On your event day you may share the
                building with Ikinari Coffee, the Gallery, Fento kitchen, and Selection Sauvage wines.
                Please treat shared areas with care and leave every space exactly as you found it.
              </p>
            </td>
          </tr>

          <!-- ③ INVOICE — tertiary -->
          {inv_html}

          <!-- Website link + T&C -->
          <tr>
            <td style="padding:0 40px 32px;">
              <hr style="border:none;border-top:1px solid #e8e4de;margin:0 0 24px;">
              <p style="margin:0 0 14px;font-size:14px;line-height:1.7;color:#666;">
                Everything you need to know about the space is at
                <a href="https://sauvage.amsterdam" style="color:#1a1a1a;font-weight:600;text-decoration:underline;">sauvage.amsterdam</a>.
                Questions before your event? Reach Greg directly:
                <a href="https://wa.me/31634742988" style="color:#1a1a1a;font-weight:600;text-decoration:underline;">WhatsApp</a>
                or <a href="tel:+31634742988" style="color:#1a1a1a;text-decoration:underline;">+31 634 742 988</a>.
              </p>
              <p style="margin:0;font-size:12px;line-height:1.6;color:#999;">
                By completing this booking you agreed to our
                <a href="https://sauvage.amsterdam/terms" style="color:#666;text-decoration:underline;">Terms &amp; Conditions</a>.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#b8860b;height:2px;font-size:0;line-height:0;">&nbsp;</td>
          </tr>
          <tr>
            <td style="background:#111111;padding:24px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="vertical-align:middle;">
                    <img src="{logo_url}" alt="Sauvage Space" width="36" height="36"
                         style="display:inline-block;width:36px;height:36px;border:0;filter:invert(1);opacity:0.7;vertical-align:middle;" />
                    <span style="font-size:12px;color:#555;margin-left:12px;vertical-align:middle;letter-spacing:1px;text-transform:uppercase;">Sauvage Space</span>
                  </td>
                  <td align="right" style="vertical-align:middle;">
                    <p style="margin:0;font-size:11px;color:#555;line-height:1.6;">
                      Potgieterstraat 47H, Amsterdam<br>
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

    # Plain-text fallback
    plain = f"""Hi {client_name},

Your Sauvage booking is confirmed.

EVENT: {event_type}
DATE:  {date_str}
TIME:  {time_str}
SPACE: {rooms_str}
GUESTS: {guest_count}
{"TOTAL: €" + str(quote_total) + " incl. VAT" if quote_total else ""}
DEPOSIT PAID: {deposit}

SHARED SPACE NOTE
Sauvage is home to several independent businesses — Ikinari Coffee, the Sauvage Gallery, Fento kitchen, and Selection Sauvage wines. Please treat all shared areas with care, stay within your booked zones, and leave the space as you found it.

CONFIRM YOUR ARRIVAL TIME
Let us know when you're planning to arrive for setup:
{arrival_url}

Everything you need: https://sauvage.amsterdam
Questions? WhatsApp Greg: https://wa.me/31634742988 / +31 634 742 988

Terms & Conditions: https://sauvage.amsterdam/terms

Sauvage · Potgieterstraat 47H · Amsterdam
"""

    try:
        # Use mixed (not alternative) when we have attachments
        if invoice_pdf:
            msg = MIMEMultipart("mixed")
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(plain, "plain"))
            alt.attach(MIMEText(html,  "html"))
            msg.attach(alt)
            # Attach PDF
            pdf_part = MIMEBase("application", "pdf")
            pdf_part.set_payload(invoice_pdf)
            encoders.encode_base64(pdf_part)
            fname = f"{invoice_number or 'invoice'}.pdf"
            pdf_part.add_header(
                "Content-Disposition", "attachment", filename=fname
            )
            msg.attach(pdf_part)
        else:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(plain, "plain"))
            msg.attach(MIMEText(html,  "html"))

        msg["Subject"] = subject
        msg["From"]    = f"Sauvage Amsterdam <{FROM_EMAIL}>"
        msg["To"]      = client_email

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"[Email] Confirmation sent to {client_email} (record {record_id})"
              + (f" + invoice {invoice_number}" if invoice_number else ""))
        return True

    except Exception as e:
        print(f"[Email] Failed to send confirmation to {client_email}: {e}")
        return False
