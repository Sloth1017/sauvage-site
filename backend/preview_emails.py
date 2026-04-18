"""
preview_emails.py — open all 4 emails in the browser without sending.
Run: python preview_emails.py
"""
import os, sys, tempfile, webbrowser
sys.path.insert(0, os.path.dirname(__file__))

# ── Fake SMTP so nothing actually sends ──────────────────────────────────────
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

# ── Patch URLs so icons/logo resolve locally ─────────────────────────────────
import event_emails as ee
import confirmation_email as ce
_repo  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_media = os.path.join(_repo, "media")
_logo  = os.path.join(_media, "sauvage-logo.png")
ee.LOGO_URL = f"file://{_logo}"
ce.LOGO_URL = f"file://{_logo}"
ee.BASE_URL = f"file://{_repo}"   # so BASE_URL/media/icon-*.png resolves correctly

# Force SMTP creds so the functions don't bail early
ce.SMTP_USER     = "preview"
ce.SMTP_PASSWORD = "preview"
ee.SMTP_USER     = "preview"
ee.SMTP_PASSWORD = "preview"

# ── Build HTML for each email ─────────────────────────────────────────────────
def _capture(fn, *args, **kwargs):
    _captured.clear()
    fn(*args, **kwargs)
    return next(iter(_captured.values()), None)

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

tmpdir = tempfile.mkdtemp()
for filename, build in emails.items():
    html = build()
    if not html:
        print(f"[!] No HTML captured for {filename} — check SMTP patch")
        continue
    path = os.path.join(tmpdir, filename)
    with open(path, "w") as f:
        f.write(html)
    webbrowser.open(f"file://{path}")
    print(f"[✓] {filename} → {path}")
