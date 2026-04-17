from flask import Flask, send_from_directory, make_response
from shopify_webhook import webhook_bp
from chat_backend import chat_bp
import os

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
        "/var/www/sauvage/widget.js",                                   # git repo (primary)
        os.path.join(os.path.dirname(__file__), "..", "widget.js"),     # repo relative path
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
    
    resp = make_response(content)
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
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

if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5001)))
