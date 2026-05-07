#!/usr/bin/env python3
"""
Generate email preview HTML files without opening browser.
Usage: python3 generate_email_previews.py
"""
import os
import sys

# Add backend directory to path so imports work
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, _backend_dir)

# ── Fake SMTP so nothing actually sends ──────────────────────────────────
import smtplib
_captured = {}

class _FakeSMTP:
    def __init__(self, *a, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def starttls(self, *a, **kw): pass
    def login(self, *a, **kw): pass
    def send_message(self, msg):
        import email as _em
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    _captured["preview"] = payload.decode()
    def sendmail(self, from_, to_, raw):
        import email as _em
        msg = _em.message_from_string(raw)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    _captured["preview"] = payload.decode()
    def quit(self): pass

smtplib.SMTP = _FakeSMTP

# ── Sample booking state ──────────────────────────────────────────────────────
STATE = {
    "client_name":    "Anna Schmidt",
    "email":          "preview@example.com",
    "event_type":     "Birthday",
    "dates":          "2026-05-10",
    "start_time":     "18:00",
    "end_time":       "23:00",
    "rooms":          ["Upstairs (Gallery)", "Entrance"],
    "guest_count":    25,
    "attributed_host":"Greg",
    "arrival_time":   "16:00",
    "booking_id":     "recPREVIEW123",
    "phone":          "+31612345678",
}

# Import email modules
import event_emails as ee
import confirmation_email as ce

# ── Patch URLs so icons/logo resolve locally ─────────────────────────────────
_repo  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_media = os.path.join(_repo, "media")

def _b64(path):
    import base64, mimetypes
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"

_logo_b64  = _b64(os.path.join(_media, "sauvage-logo.png"))
_gcal_b64  = _b64(os.path.join(_media, "icon-google-calendar.png"))
_ical_b64  = _b64(os.path.join(_media, "icon-apple-calendar.png"))

ee.LOGO_URL = _logo_b64
ce.LOGO_URL = _logo_b64
ee.BASE_URL = f"file://{_repo}"
ce.BASE_URL = f"file://{_repo}"

# Patch calendar widget to use embedded images
_orig_cal = ee._calendar_widget
def _patched_cal(title, date_str, start_time, end_time, description=""):
    result = _orig_cal(title, date_str, start_time, end_time, description)
    result = result.replace(f"file://{_repo}/media/icon-google-calendar.png", _gcal_b64)
    result = result.replace(f"file://{_repo}/media/icon-apple-calendar.png", _ical_b64)
    return result
ee._calendar_widget = _patched_cal

# Force SMTP creds so the functions don't bail early
ce.SMTP_USER     = "preview"
ce.SMTP_PASSWORD = "preview"
ee.SMTP_USER     = "preview"
ee.SMTP_PASSWORD = "preview"

# ── Build HTML for each email ─────────────────────────────────────────────────
def _capture(fn, *args, **kwargs):
    _captured.clear()
    fn(*args, **kwargs)
    html = next(iter(_captured.values()), None)
    if html:
        # Replace file:// URLs with embedded base64
        html = html.replace(f"file://{_repo}/media/icon-google-calendar.png", _gcal_b64)
        html = html.replace(f"file://{_repo}/media/icon-apple-calendar.png",  _ical_b64)
        html = html.replace(f"file://{_repo}/media/sauvage-logo.png",         _logo_b64)
        # Replace CID references with embedded base64
        html = html.replace("cid:logo@sauvage.amsterdam", _logo_b64)
        html = html.replace("cid:gcal@sauvage.amsterdam", _gcal_b64)
        html = html.replace("cid:ical@sauvage.amsterdam", _ical_b64)
    return html

emails = {
    "1_confirmation.html": lambda: _capture(
        ce.send_booking_confirmation,
        record_id      = "recPREVIEW123",
        state          = STATE,
        invoice_number = "INV-2026-001",
        invoice_url    = "https://sauvage.amsterdam/invoice/INV-2026-001?t=preview",
    ),
    "2_day_before.html":   lambda: _capture(ee.send_day_before,   STATE),
    "3_day_of.html":       lambda: _capture(ee.send_day_of,       STATE),
    "4_day_after.html":    lambda: _capture(ee.send_day_after,    STATE),
}

outdir = os.path.dirname(__file__)
for filename, build in emails.items():
    html = build()
    if not html:
        print(f"[!] No HTML captured for {filename}")
        continue
    path = os.path.join(outdir, filename)
    with open(path, "w") as f:
        f.write(html)
    print(f"[✓] {filename}")

print(f"\n✓ All email previews generated in: {outdir}/")
