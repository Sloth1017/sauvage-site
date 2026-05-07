"""
balance_email.py
----------------
Sends a branded balance payment request email to the client.

Called by send_balance_request.py (daily cron) when a confirmed
booking has an outstanding balance due within 7 days of the event.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime as _dt

SMTP_SERVER    = os.getenv("SMTP_SERVER",    "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT",  "587"))
SMTP_USER      = os.getenv("SMTP_USER",      "")
SMTP_PASSWORD  = os.getenv("SMTP_PASSWORD",  "")
FROM_EMAIL     = os.getenv("FROM_EMAIL",     "bookings@sauvage.amsterdam")
BASE_URL       = os.getenv("BASE_URL",       "https://sauvage.amsterdam")


def _fmt_date(raw: str) -> str:
    try:
        return _dt.strptime(raw.strip()[:10], "%Y-%m-%d").strftime("%A %-d %B %Y")
    except Exception:
        return raw


def _fmt_rooms(rooms) -> str:
    if isinstance(rooms, list):
        return ", ".join(str(r) for r in rooms)
    return str(rooms or "TBC")


def _cid_attach(rel_path: str, cid: str, parts: list):
    """Attach an inline CID image; return its src."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", rel_path),
        os.path.join(os.path.dirname(__file__), rel_path),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    data = f.read()
                part = MIMEImage(data, _subtype="png")
                part.add_header("Content-ID", f"<{cid}>")
                part.add_header("Content-Disposition", "inline",
                                filename=os.path.basename(p))
                parts.append(part)
                return f"cid:{cid}"
            except Exception:
                pass
    return f"{BASE_URL}/{rel_path}"


def send_balance_request(
    record_id:     str,
    client_name:   str,
    client_email:  str,
    event_type:    str,
    event_date:    str,
    start_time:    str,
    end_time:      str,
    rooms,
    guest_count,
    balance_eur:   str,
    total_eur:     str,
    deposit_eur:   str,
    payment_url:   str,
    days_until:    int,
) -> bool:
    """Send the branded balance request email. Returns True on success."""

    if not client_email:
        print("[BalanceEmail] No client email — skipping")
        return False
    if not SMTP_USER or not SMTP_PASSWORD:
        print("[BalanceEmail] SMTP not configured — skipping")
        return False

    date_str  = _fmt_date(event_date)
    rooms_str = _fmt_rooms(rooms)
    time_str  = f"{start_time} to {end_time}" if start_time and end_time else start_time or "TBC"
    day_label = f"{days_until} day{'s' if days_until != 1 else ''}"

    urgency_note = (
        "Your event is <strong>tomorrow</strong> — please complete payment now."
        if days_until == 1
        else f"Your event is in <strong>{day_label}</strong>. Please complete payment before it arrives."
    )

    _cid_parts = []
    logo_src = _cid_attach("media/sauvage-logo.png", "logo@sauvage.amsterdam", _cid_parts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Balance Due – Sauvage Space</title>
</head>
<body style="margin:0;padding:0;background:#f5f3ef;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;color:#1a1a1a;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f5f3ef;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;width:100%;background:#ffffff;border-radius:4px;
                      overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background:#1a1a1a;padding:28px 40px 24px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="vertical-align:middle;">
                    <img src="{logo_src}" alt="Sauvage Space" width="101" height="101"
                         style="display:block;width:101px;height:101px;border:0;" />
                  </td>
                  <td style="vertical-align:middle;padding-left:20px;">
                    <p style="margin:0 0 4px;font-size:11px;letter-spacing:3px;
                               text-transform:uppercase;color:#666;font-weight:500;">
                      Potgieterstraat 47H, Amsterdam
                    </p>
                    <h1 style="margin:0;font-size:24px;font-weight:400;color:#ffffff;
                                letter-spacing:-0.2px;">Balance Due</h1>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Gold accent -->
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
                Almost there. Your Sauvage booking is confirmed — there's just the remaining balance
                to settle before your event. {urgency_note}
              </p>
            </td>
          </tr>

          <!-- Booking summary -->
          <tr>
            <td style="padding:0 40px 32px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:#f5f3ef;border-radius:4px;padding:24px;">
                <tr>
                  <td style="padding:0 24px;">
                    <p style="margin:0 0 4px;font-size:11px;letter-spacing:2px;
                               text-transform:uppercase;color:#999;font-weight:600;">Your Event</p>
                    <p style="margin:0 0 20px;font-size:17px;font-weight:500;color:#1a1a1a;">
                      {event_type}
                    </p>
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;
                                     text-transform:uppercase;color:#aaa;">Date</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">
                            {date_str}
                          </p>
                        </td>
                        <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;
                                     text-transform:uppercase;color:#aaa;">Time</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">
                            {time_str}
                          </p>
                        </td>
                      </tr>
                      <tr>
                        <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;
                                     text-transform:uppercase;color:#aaa;">Space</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">
                            {rooms_str}
                          </p>
                        </td>
                        <td width="50%" style="padding:0 0 12px;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;
                                     text-transform:uppercase;color:#aaa;">Guests</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">
                            {guest_count}
                          </p>
                        </td>
                      </tr>
                      <tr>
                        <td width="50%" style="padding:0;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;
                                     text-transform:uppercase;color:#aaa;">Total</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">
                            &#8364;{total_eur} incl. VAT
                          </p>
                        </td>
                        <td width="50%" style="padding:0;vertical-align:top;">
                          <p style="margin:0 0 2px;font-size:11px;letter-spacing:1.5px;
                                     text-transform:uppercase;color:#aaa;">Deposit Paid</p>
                          <p style="margin:0;font-size:14px;color:#1a1a1a;font-weight:500;">
                            &#8364;{deposit_eur}
                          </p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Payment CTA -->
          <tr>
            <td style="padding:0 40px 32px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:#1a1a18;border-radius:2px;overflow:hidden;">
                <tr>
                  <td style="background:#b8860b;height:3px;font-size:0;line-height:0;"></td>
                </tr>
                <tr>
                  <td style="padding:32px 36px 36px;">
                    <p style="margin:0 0 8px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                               font-size:9px;letter-spacing:0.22em;text-transform:uppercase;color:#b8860b;">
                      Balance due
                    </p>
                    <p style="margin:0 0 10px;font-family:Georgia,serif;font-size:32px;
                               font-weight:300;color:#ffffff;line-height:1.1;">
                      &#8364;{balance_eur}
                    </p>
                    <p style="margin:0 0 28px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                               font-size:13px;line-height:1.7;color:rgba(255,255,255,0.5);">
                      Pay securely by card or iDEAL. Takes less than a minute.
                    </p>
                    <a href="{payment_url}"
                       style="display:block;background:#ffffff;color:#1a1a18;text-decoration:none;
                              padding:16px 0;border-radius:1px;text-align:center;
                              font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
                              font-size:10px;font-weight:700;letter-spacing:0.22em;
                              text-transform:uppercase;">
                      Pay &#8364;{balance_eur} now &rarr;
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer note -->
          <tr>
            <td style="padding:0 40px 32px;">
              <hr style="border:none;border-top:1px solid #e8e4de;margin:0 0 24px;">
              <p style="margin:0 0 14px;font-size:14px;line-height:1.7;color:#666;">
                Questions? Reach Greg directly:
                <a href="https://wa.me/31634742988"
                   style="color:#1a1a1a;font-weight:600;text-decoration:underline;">WhatsApp</a>
                or <a href="tel:+31634742988"
                      style="color:#1a1a1a;text-decoration:underline;">+31 634 742 988</a>.
              </p>
              <p style="margin:0;font-size:12px;line-height:1.6;color:#999;">
                <a href="https://sauvage.amsterdam/terms"
                   style="color:#666;text-decoration:underline;">Terms &amp; Conditions</a>
              </p>
            </td>
          </tr>

          <!-- Footer bar -->
          <tr>
            <td style="background:#b8860b;height:2px;font-size:0;line-height:0;">&nbsp;</td>
          </tr>
          <tr>
            <td style="background:#111111;padding:24px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="vertical-align:middle;">
                    <img src="{logo_src}" alt="Sauvage Space" width="36" height="36"
                         style="display:inline-block;width:36px;height:36px;border:0;
                                opacity:0.7;vertical-align:middle;" />
                    <span style="font-size:12px;color:#555;margin-left:12px;
                                 vertical-align:middle;letter-spacing:1px;
                                 text-transform:uppercase;">Sauvage Space</span>
                  </td>
                  <td align="right" style="vertical-align:middle;">
                    <p style="margin:0;font-size:11px;color:#555;line-height:1.6;">
                      Potgieterstraat 47H, Amsterdam<br>
                      <a href="https://sauvage.amsterdam"
                         style="color:#888;text-decoration:none;">sauvage.amsterdam</a>
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
  <img src="{BASE_URL}/track/open?tid=__TRACKING_ID__"
       width="1" height="1" border="0" style="display:block;width:1px;height:1px;" alt="">
</body>
</html>"""

    plain = f"""Hi {client_name},

Your Sauvage booking is confirmed — there's just the remaining balance to settle.

EVENT:   {event_type}
DATE:    {date_str}
TIME:    {time_str}
SPACE:   {rooms_str}
GUESTS:  {guest_count}

TOTAL:         €{total_eur} incl. VAT
DEPOSIT PAID:  €{deposit_eur}
BALANCE DUE:   €{balance_eur}

Pay now (card or iDEAL):
{payment_url}

Questions? WhatsApp Greg: https://wa.me/31634742988 / +31 634 742 988
Terms & Conditions: https://sauvage.amsterdam/terms

Sauvage · Potgieterstraat 47H · Amsterdam
"""

    # Inject email open tracking
    try:
        from airtable_client import create_email_tracking
        tid = create_email_tracking(record_id, "balance_request")
        html = html.replace("__TRACKING_ID__", tid)
    except Exception:
        html = html.replace("__TRACKING_ID__", "")

    try:
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(plain, "plain"))
        alt.attach(MIMEText(html,  "html"))

        related = MIMEMultipart("related")
        related.attach(alt)
        for part in _cid_parts:
            related.attach(part)

        msg = MIMEMultipart("mixed")
        msg.attach(related)

        msg["Subject"] = f"Balance due — {event_type} on {date_str}"
        msg["From"]    = f"Sauvage Amsterdam <{FROM_EMAIL}>"
        msg["To"]      = client_email
        msg["Bcc"]     = "hello@rootsandremedies.earth"

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"[BalanceEmail] Sent to {client_email} — €{balance_eur} due")
        return True

    except Exception as e:
        print(f"[BalanceEmail] Send failed: {e}")
        return False
