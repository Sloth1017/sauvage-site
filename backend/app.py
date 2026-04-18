from flask import Flask, send_from_directory, make_response, abort, send_file, request, Response
from shopify_webhook import webhook_bp
from chat_backend import chat_bp
import os
import json
import datetime

app = Flask(__name__)
app.register_blueprint(webhook_bp)
app.register_blueprint(chat_bp)

# ── Static site directories ───────────────────────────────────────────────────
# Serve the hub website from the workspace sauvage folder
SITE_DIR = "/home/greg/.openclaw/workspace/sauvage"

@app.route("/health")
def health():
    return {"status": "ok"}, 200

@app.route("/widget.js")
def widget():
    # Load widget.js and replace API endpoint dynamically.
    # Try paths in priority order — git repo first so deploys take effect immediately.
    _widget_candidates = [
        "/root/sauvage/widget.js",                                      # git repo (primary)
        os.path.join(os.path.dirname(__file__), "..", "widget.js"),     # repo relative path
        "/var/www/sauvage/widget.js",                                   # legacy static copy
        "/home/greg/.openclaw/workspace/sauvage/widget.js",            # legacy workspace
        os.path.join(os.path.dirname(__file__), "widget.js"),          # backend dir fallback
    ]
    content = None
    for _path in _widget_candidates:
        try:
            with open(_path, 'r') as f:
                content = f.read()
            break
        except OSError:
            continue
    if content is None:
        return "// Error loading widget.js", 500, {"Content-Type": "application/javascript"}
    
    # Ensure the API endpoint is correct
    content = content.replace(
        'const API = "https://booking.selectionsauvage.nl"',
        'const API = "https://sauvage.amsterdam"'
    )
    
    import hashlib
    etag = hashlib.md5(content.encode()).hexdigest()
    resp = make_response(content)
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["ETag"] = etag
    return resp

@app.route("/terms")
def terms():
    return send_from_directory(os.path.dirname(__file__), "terms.html",
                               mimetype="text/html")

@app.route("/")
def index():
    return send_from_directory(SITE_DIR, "index.html", mimetype="text/html")

@app.route("/media/photos/<path:filename>")
def photos(filename):
    return send_from_directory(os.path.join(SITE_DIR, "media", "photos"), filename)

@app.route("/media/<path:filename>")
def media(filename):
    return send_from_directory(os.path.join(SITE_DIR, "media"), filename)

@app.route("/fonts/<path:filename>")
def fonts(filename):
    return send_from_directory(os.path.join(SITE_DIR, "fonts"), filename)

# ── Invoice serving ───────────────────────────────────────────────────────────
_INV_DIR = os.path.join(os.path.dirname(__file__), "invoices")

@app.route("/invoice/<invoice_number>")
def serve_invoice(invoice_number):
    """Serve a PDF invoice — HMAC-token gated so only the URL recipient can access it."""
    from flask import request as _req
    from invoice_generator import verify_invoice_token
    token = _req.args.get("t", "")
    if not verify_invoice_token(invoice_number, token):
        abort(403)
    path = os.path.join(_INV_DIR, f"{invoice_number}.pdf")
    if not os.path.exists(path):
        abort(404)
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"{invoice_number}.pdf",
    )


# ── Wine click tracking ───────────────────────────────────────────────────────
_WINE_CLICKS_LOG = os.path.join(os.path.dirname(__file__), "wine_clicks.jsonl")

@app.route("/wines")
def wines():
    booking_id = request.args.get("booking", "")
    ref        = request.args.get("ref", "")
    data = {
        "ts":      datetime.datetime.utcnow().isoformat(),
        "booking": booking_id,
        "name":    request.args.get("name", ""),
        "email":   request.args.get("email", ""),
        "event":   request.args.get("event", ""),
        "ref":     ref,
    }
    with open(_WINE_CLICKS_LOG, "a") as f:
        f.write(json.dumps(data) + "\n")

    if booking_id:
        try:
            from airtable_client import update_inquiry
            update_inquiry(booking_id, {
                "Wine Interest":        True,
                "Wine Interest Source": f"{ref} — {data['ts'][:10]}",
            })
        except Exception as e:
            print(f"[Wines] Airtable update failed for {booking_id}: {e}")

    from flask import redirect
    return redirect("https://www.selectionsauvage.nl/")


# ── Calendar ICS download ─────────────────────────────────────────────────────
@app.route("/calendar.ics")
def calendar_ics():
    title       = request.args.get("title",       "Sauvage Event")
    start       = request.args.get("start",       "")
    end         = request.args.get("end",         "")
    location    = request.args.get("location",    "Potgieterstraat 47H, Amsterdam")
    description = request.args.get("description", "")

    uid = f"{start}-sauvage@sauvage.amsterdam"
    now = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Sauvage Amsterdam//EN\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{now}\r\n"
        f"DTSTART:{start}\r\n"
        f"DTEND:{end}\r\n"
        f"SUMMARY:{title}\r\n"
        f"LOCATION:{location}\r\n"
        f"DESCRIPTION:{description}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return Response(
        ics,
        mimetype="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="sauvage-event.ics"'},
    )


# ── Feedback form submission ──────────────────────────────────────────────────
_FEEDBACK_LOG = os.path.join(os.path.dirname(__file__), "feedback.jsonl")

@app.route("/feedback", methods=["POST"])
def feedback():
    data = {
        "ts":        datetime.datetime.utcnow().isoformat(),
        "name":      request.form.get("name", ""),
        "event":     request.form.get("event", ""),
        "booking":   request.form.get("booking", ""),
        "rating":    request.form.get("rating", ""),
        "highlight": request.form.get("highlight", ""),
        "improve":   request.form.get("improve", ""),
        "comment":   request.form.get("comment", ""),
    }
    with open(_FEEDBACK_LOG, "a") as f:
        f.write(json.dumps(data) + "\n")

    try:
        from airtable_client import submit_feedback
        submit_feedback(
            booking_record_id = data["booking"],
            client_name       = data["name"],
            event_type        = data["event"],
            rating            = data["rating"],
            highlight         = data["highlight"],
            improve           = data["improve"],
            comment           = data["comment"],
        )
    except Exception as e:
        print(f"[Feedback] Airtable write failed (non-fatal): {e}")

    return Response("""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Thank you</title></head>
<body style="margin:0;padding:60px 24px;background:#f7f4ef;font-family:Georgia,serif;text-align:center;">
  <p style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#8b6f47;margin:0 0 16px;">Sauvage Amsterdam</p>
  <h1 style="font-size:28px;font-weight:300;font-style:italic;color:#1a1a18;margin:0 0 16px;">Thank you.</h1>
  <p style="font-size:15px;color:#6b6560;max-width:360px;margin:0 auto;line-height:1.75;">
    Your feedback has been received. We read every response personally and it shapes how we improve the space.
  </p>
</body></html>""", mimetype="text/html")


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5001)))
