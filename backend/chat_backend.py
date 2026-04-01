"""
chat_backend.py
---------------
Flask blueprint powering the Sauvage booking chatbot.
Calls the Anthropic API with the full system prompt and maintains
per-session conversation history in memory.

Routes:
    POST /chat                          — send a message, get a response
    POST /chat/reset                    — clear a session
    GET  /chat/session                  — get a new session ID
    GET  /chat/payment-status/<sid>     — poll for deposit confirmation
"""

import os
import re
import uuid
import json
from flask import Blueprint, request, jsonify
import anthropic

# ── Blueprint ─────────────────────────────────────────────────────────────────
chat_bp = Blueprint("chat", __name__)

# ── Anthropic client ──────────────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── In-memory session store ───────────────────────────────────────────────────
# { session_id: [{"role": "user"|"assistant", "content": "..."}] }
sessions: dict = {}

# ── Per-session booking state cache ──────────────────────────────────────────
# { session_id: {event_type, dates, times, name, email, ...} }
session_states: dict = {}

# ── Per-session integration metadata ─────────────────────────────────────────
# { session_id: { record_id, draft_order_id, payment_url, last_pushed } }
session_meta: dict = {}

# ── Static deposit URLs (used by the bot, replaced with dynamic links) ────────
DEPOSIT_URL_STD = "https://www.selectionsauvage.nl/products/event-deposit"
DEPOSIT_URL_KIT = "https://www.selectionsauvage.nl/products/event-deposit-copy"

# ── Optional integrations (graceful degradation if not configured) ────────────
_AIRTABLE_ENABLED = False
_SHOPIFY_ENABLED  = False

try:
    from airtable_client import (
        create_inquiry, update_inquiry, mark_deposit_pending,
        get_inquiry_by_session,
    )
    _AIRTABLE_ENABLED = bool(os.getenv("AIRTABLE_API_KEY") or True)
except ImportError:
    pass

try:
    from shopify_client import create_checkout_session as _shopify_create_checkout
    _SHOPIFY_ENABLED = bool(os.getenv("SHOPIFY_ADMIN_API_TOKEN") or True)
except ImportError:
    pass

# ── Google Calendar integration ───────────────────────────────────────────────
_GCAL_ENABLED = False
try:
    from google_calendar import availability_summary, get_booked_events, calendar_snapshot
    _GCAL_ENABLED = True
    print("[Calendar] Google Calendar integration loaded ✓")
except ImportError as e:
    print(f"[Calendar] Not available: {e}")

# ── System prompt (reloaded on every request so edits go live without restart) ─
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "sauvage-chatbot-prompt-v2_1.md")
_PROMPT_CACHE: dict = {"mtime": 0, "text": "You are the booking assistant for Sauvage Event Space in Amsterdam."}

def _load_system_prompt() -> str:
    try:
        mtime = os.path.getmtime(_PROMPT_PATH)
        if mtime != _PROMPT_CACHE["mtime"]:
            with open(_PROMPT_PATH, "r") as f:
                _PROMPT_CACHE["text"] = f.read()
            _PROMPT_CACHE["mtime"] = mtime
    except OSError:
        pass
    return _PROMPT_CACHE["text"]

# ── Booking state extraction ──────────────────────────────────────────────────

_STATE_LABELS = {
    "event_type":     "Event type",
    "dates":          "Date(s)",
    "start_time":     "Start time",
    "end_time":       "End time",
    "is_multi_day":   "Multi-day / continuous event",
    "client_name":    "Client name",
    "email":          "Email",
    "phone":          "Phone / WhatsApp",
    "guest_count":    "Guest count",
    "customer_type":  "Booking type (private or business)",
    "rooms":          "Rooms selected",
}

_EXTRACT_SYSTEM = (
    "You are a data extraction assistant. Given a booking conversation, extract ONLY "
    "facts that have been clearly confirmed by the client. Return a single JSON object "
    "with these keys (omit any that are not yet confirmed): "
    "event_type, dates, start_time, end_time, is_multi_day, client_name, email, phone, "
    "guest_count, customer_type, rooms. "
    "Use plain strings. For dates use e.g. 'Thu 9 Apr, Fri 10 Apr'. "
    "Return ONLY the JSON object, no explanation."
)

def _extract_booking_state(history: list) -> dict:
    """Use a fast Haiku call to extract confirmed booking facts from the conversation."""
    if len(history) < 2:
        return {}
    convo = "\n".join(
        f"{'CLIENT' if m['role'] == 'user' else 'BOT'}: {m['content'][:300]}"
        for m in history[-20:]
    )
    try:
        r = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": convo}],
        )
        text = r.content[0].text.strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            return {k: v for k, v in parsed.items() if v not in (None, "", [], {})}
    except Exception:
        pass
    return {}

def _state_block(state: dict) -> str:
    """Format the confirmed state as a prompt block injected before the main prompt."""
    if not state:
        return ""
    lines = [
        "## ⚡ CONFIRMED BOOKING FACTS — DO NOT RE-ASK ANY OF THESE",
        "The following has already been confirmed in this conversation.",
        "Treat every item below as final. Do not ask for it again. Move to what is still unknown.",
        "",
    ]
    for key, label in _STATE_LABELS.items():
        if key in state:
            lines.append(f"- **{label}**: {state[key]}")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)

# ── Airtable helpers ──────────────────────────────────────────────────────────

def _ensure_airtable_record(session_id: str, state: dict) -> str | None:
    """Create an Airtable inquiry record the first time we have an event type."""
    if not _AIRTABLE_ENABLED:
        return None
    meta = session_meta.setdefault(session_id, {})
    if "record_id" not in meta and state.get("event_type"):
        try:
            record_id = create_inquiry(session_id, state["event_type"])
            meta["record_id"] = record_id
            print(f"Airtable inquiry created: {record_id} for session {session_id}")
        except Exception as e:
            print(f"Airtable create_inquiry error: {e}")
    return meta.get("record_id")

def _sync_airtable(session_id: str, state: dict) -> None:
    """Push any newly confirmed fields to Airtable (only changed fields)."""
    if not _AIRTABLE_ENABLED:
        return
    record_id = _ensure_airtable_record(session_id, state)
    if not record_id:
        return
    meta = session_meta[session_id]
    last = meta.get("last_pushed", {})

    # Map state keys → Airtable field names
    field_map = {
        "client_name":   "Client Name",
        "email":         "Email",
        "phone":         "Phone",
        "guest_count":   "Guest Count",
        "customer_type": "Customer Type",
        "dates":         "Requested Date",
        "start_time":    "Start Time",
        "end_time":      "End Time",
    }
    updates = {}
    for key, at_field in field_map.items():
        val = state.get(key)
        if val and val != last.get(key):
            updates[at_field] = val

    if updates:
        try:
            update_inquiry(record_id, updates)
            meta["last_pushed"] = {**last, **{k: state[k] for k in field_map if state.get(k)}}
        except Exception as e:
            print(f"Airtable sync error: {e}")

# ── Shopify checkout injection ────────────────────────────────────────────────

def _inject_checkout_url(session_id: str, state: dict, bot_response: str) -> str:
    """
    If the bot's response contains a static deposit URL, replace it with a
    session-linked Shopify Draft Order invoice URL — creating the draft order
    on first call, reusing it on subsequent renders.

    Falls back to the static URL if Shopify/Airtable isn't configured or
    if required client details (email) aren't yet known.
    """
    # Only act when the bot has included a payment link
    if DEPOSIT_URL_STD not in bot_response and DEPOSIT_URL_KIT not in bot_response:
        return bot_response

    if not _SHOPIFY_ENABLED or not _AIRTABLE_ENABLED:
        return bot_response

    meta = session_meta.setdefault(session_id, {})

    # Reuse an existing draft order URL if already created for this session
    if meta.get("payment_url"):
        url = meta["payment_url"]
        bot_response = bot_response.replace(DEPOSIT_URL_KIT, url)
        bot_response = bot_response.replace(DEPOSIT_URL_STD, url)
        return bot_response

    # Need email to create a Shopify checkout
    client_email = state.get("email", "")
    if not client_email:
        return bot_response

    record_id = _ensure_airtable_record(session_id, state)
    if not record_id:
        return bot_response

    kitchen_booked = DEPOSIT_URL_KIT in bot_response
    client_name    = state.get("client_name", "Guest")
    event_type     = state.get("event_type", "Event")
    event_date     = state.get("dates", "")

    try:
        result = _shopify_create_checkout(
            airtable_record_id = record_id,
            client_email       = client_email,
            client_name        = client_name,
            event_type         = event_type,
            event_date         = event_date,
            kitchen_booked     = kitchen_booked,
            session_id         = session_id,
        )
        payment_url = result["payment_url"]
        meta["draft_order_id"] = result["draft_order_id"]
        meta["payment_url"]    = payment_url

        # Replace both static URLs in case the bot included both
        bot_response = bot_response.replace(DEPOSIT_URL_KIT, payment_url)
        bot_response = bot_response.replace(DEPOSIT_URL_STD, payment_url)

        # Mark pending in Airtable
        try:
            mark_deposit_pending(record_id, f"shopify-draft-{result['draft_order_id']}")
        except Exception as e:
            print(f"mark_deposit_pending error: {e}")

        print(f"Shopify draft order {result['draft_order_id']} linked to session {session_id}")

    except Exception as e:
        print(f"Shopify checkout creation error: {e}")
        # Return original response — static URL is still valid as fallback

    return bot_response

# ── CORS headers ──────────────────────────────────────────────────────────────
def _cors_headers():
    return {
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

# ── Routes ────────────────────────────────────────────────────────────────────

GREETING = (
    "Hey! Welcome to Sauvage 👋\n\n"
    "I'm the booking assistant for Sauvage Event Space — Potgieterstraat 47H, Amsterdam.\n\n"
    "I can check availability, build your quote, and lock in your booking with a deposit — "
    "all right here, no emails needed.\n\n"
    "What kind of event are you planning?"
)

@chat_bp.route("/chat/session", methods=["GET", "OPTIONS"])
def new_session():
    if request.method == "OPTIONS":
        return "", 200, _cors_headers()
    session_id = str(uuid.uuid4())
    sessions[session_id]      = [{"role": "assistant", "content": GREETING}]
    session_states[session_id] = {}
    session_meta[session_id]   = {}
    return jsonify({"session_id": session_id}), 200, _cors_headers()


@chat_bp.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return "", 200, _cors_headers()

    data       = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    message    = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "message is required"}), 400, _cors_headers()

    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id]      = []
        session_states[session_id] = {}
        session_meta[session_id]   = {}

    sessions[session_id].append({"role": "user", "content": message})
    history = sessions[session_id][-40:]

    # Extract confirmed booking state and MERGE with accumulated state
    # Never overwrite — once a field is confirmed it stays, even if a short
    # follow-up message (like "Yes") doesn't re-surface it in extraction
    new_state = _extract_booking_state(history)
    accumulated = session_states.get(session_id, {})
    state = {**accumulated, **new_state}   # new extraction takes precedence, old survives gaps
    session_states[session_id] = state

    # Push new state to Airtable (async-style: best-effort, non-blocking)
    try:
        _sync_airtable(session_id, state)
    except Exception as e:
        print(f"_sync_airtable error: {e}")

    # Inject live calendar availability into system prompt
    calendar_block = ""
    if _GCAL_ENABLED:
        try:
            # Extract any ISO dates mentioned in the recent conversation
            date_pattern = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')
            mentioned_dates = list(dict.fromkeys(date_pattern.findall(
                " ".join(m["content"] for m in history[-10:])
            )))

            # Also detect rooms mentioned recently
            recent_text = " ".join(m["content"] for m in history[-10:]).lower()
            requested_rooms = []
            if any(x in recent_text for x in ["entrance", "front", "bar"]):
                requested_rooms.append("entrance")
            if any(x in recent_text for x in ["gallery", "upstairs"]):
                requested_rooms.append("gallery")
            if "kitchen" in recent_text:
                requested_rooms.append("kitchen")
            if "cave" in recent_text:
                requested_rooms.append("cave")
            if not requested_rooms:
                requested_rooms = ["entrance", "gallery", "kitchen", "cave"]

            # Also extract times mentioned
            time_pattern = re.compile(r'\b(\d{1,2}:\d{2})\b')
            mentioned_times = list(dict.fromkeys(time_pattern.findall(
                " ".join(m["content"] for m in history[-6:])
            )))
            start_time = mentioned_times[0] if len(mentioned_times) >= 1 else None
            end_time   = mentioned_times[1] if len(mentioned_times) >= 2 else None

            # Pad to HH:MM if needed
            if start_time and len(start_time) < 5:
                start_time = start_time.zfill(5)
            if end_time and len(end_time) < 5:
                end_time = end_time.zfill(5)

            if mentioned_dates:
                avail = availability_summary(
                    mentioned_dates, requested_rooms, start_time, end_time
                )
                calendar_block = (
                    f"\n\n## LIVE CALENDAR CHECK (per room + time slot)\n"
                    f"{avail}\n"
                    f"RULES:\n"
                    f"- Each room is independently bookable\n"
                    f"- Two clients CAN book the same date if they use different rooms\n"
                    f"- Two clients CAN book the same room on the same date if their times DON'T overlap\n"
                    f"- Only flag a conflict when the SAME room has an OVERLAPPING time slot\n"
                    f"- If a conflict exists, offer the alternative slots shown above\n"
                )
            else:
                snapshot = calendar_snapshot(60)
                calendar_block = (
                    f"\n\n## LIVE CALENDAR SNAPSHOT (next 60 days, per room)\n"
                    f"{snapshot}\n"
                    f"RULES:\n"
                    f"- Each room is independently bookable\n"
                    f"- Multiple clients can be at Sauvage simultaneously in different rooms\n"
                    f"- A conflict only exists when the SAME room has OVERLAPPING times\n"
                    f"- Never block a whole date just because one room is taken\n"
                )
        except Exception as e:
            print(f"[Calendar] Error generating block: {e}")

    full_system = _state_block(state) + calendar_block + _load_system_prompt()

    try:
        response = client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = 2048,
            system     = full_system,
            messages   = history,
        )
        assistant_text = response.content[0].text
    except Exception as e:
        return jsonify({"error": str(e)}), 500, _cors_headers()

    # Replace static deposit URL with a session-linked Shopify checkout URL
    try:
        assistant_text = _inject_checkout_url(session_id, state, assistant_text)
    except Exception as e:
        print(f"_inject_checkout_url error: {e}")

    sessions[session_id].append({"role": "assistant", "content": assistant_text})

    return jsonify({
        "session_id":    session_id,
        "response":      assistant_text,
        "message_count": len(sessions[session_id]),
    }), 200, _cors_headers()


@chat_bp.route("/chat/payment-status/<session_id>", methods=["GET", "OPTIONS"])
def payment_status(session_id):
    """
    Widget polls this endpoint after the payment link is shown.
    Returns {"status": "pending"|"confirmed"|"unknown"}.
    Checks Airtable as the source of truth — the Shopify webhook updates it on payment.
    """
    if request.method == "OPTIONS":
        return "", 200, _cors_headers()

    meta   = session_meta.get(session_id, {})
    status = "unknown"

    # DEV: in-memory test-confirm flag
    if meta.get("_test_confirmed"):
        return jsonify({
            "session_id": session_id,
            "status":     "confirmed",
        }), 200, _cors_headers()

    if not meta.get("record_id"):
        # No Airtable record yet — payment link hasn't been sent
        return jsonify({
            "session_id": session_id,
            "status":     status,
        }), 200, _cors_headers()

    if _AIRTABLE_ENABLED:
        try:
            record = get_inquiry_by_session(session_id)
            if record:
                booking_status = record.get("fields", {}).get("Booking Status", "")
                if booking_status == "confirmed":
                    status = "confirmed"
                elif booking_status in ("deposit_pending", "inquiry"):
                    status = "pending"
        except Exception as e:
            print(f"payment_status Airtable check error: {e}")
            status = "pending"
    else:
        status = "pending"

    return jsonify({
        "session_id":     session_id,
        "status":         status,
        "draft_order_id": meta.get("draft_order_id"),
    }), 200, _cors_headers()


@chat_bp.route("/chat/test-confirm/<session_id>", methods=["POST", "OPTIONS"])
def test_confirm(session_id):
    """
    DEV ONLY — simulate Shopify payment confirmation without a real transaction.
    Directly marks the Airtable record as confirmed so the widget poll picks it up.
    Remove this endpoint before going live.
    """
    if request.method == "OPTIONS":
        return "", 200, _cors_headers()

    meta      = session_meta.get(session_id, {})
    record_id = meta.get("record_id")

    if record_id and _AIRTABLE_ENABLED:
        try:
            confirm_booking(record_id)
            return jsonify({
                "status":     "confirmed",
                "session_id": session_id,
                "record_id":  record_id,
            }), 200, _cors_headers()
        except Exception as e:
            return jsonify({"error": str(e)}), 500, _cors_headers()
    else:
        # Airtable not wired — just fake the status in-memory so the poll endpoint returns confirmed
        if session_id not in session_meta:
            session_meta[session_id] = {}
        session_meta[session_id]["_test_confirmed"] = True
        return jsonify({
            "status":     "confirmed",
            "session_id": session_id,
            "note":       "Airtable not enabled — in-memory flag set",
        }), 200, _cors_headers()


@chat_bp.route("/admin/calendar", methods=["POST", "OPTIONS"])
def admin_calendar():
    """
    Admin endpoint — manage calendar bookings via simple commands.
    Protected by ADMIN_SECRET env var.

    POST body: { "secret": "...", "command": "...", "params": {...} }

    Commands:
      list                          — upcoming 60 days
      check  { dates, rooms }       — availability check
      cancel { event_id }           — delete a calendar event
      create { client_name, event_type, rooms, start, end, guests, email }
    """
    if request.method == "OPTIONS":
        return "", 200, _cors_headers()

    admin_secret = os.getenv("ADMIN_SECRET", "")
    data         = request.get_json(silent=True) or {}

    if admin_secret and data.get("secret") != admin_secret:
        return jsonify({"error": "Unauthorized"}), 401, _cors_headers()

    command = data.get("command", "")
    params  = data.get("params", {})

    if not _GCAL_ENABLED:
        return jsonify({"error": "Calendar integration not available"}), 503, _cors_headers()

    try:
        if command == "list":
            from google_calendar import calendar_snapshot
            return jsonify({"result": calendar_snapshot(60)}), 200, _cors_headers()

        elif command == "check":
            from google_calendar import availability_summary
            dates = params.get("dates", [])
            rooms = params.get("rooms", None)
            return jsonify({"result": availability_summary(dates, rooms)}), 200, _cors_headers()

        elif command == "cancel":
            from google_calendar_write import cancel_booking as _cancel
            event_id = params.get("event_id", "")
            if not event_id:
                return jsonify({"error": "event_id required"}), 400, _cors_headers()
            _cancel(event_id)
            return jsonify({"result": f"Event {event_id} cancelled ✓"}), 200, _cors_headers()

        elif command == "create":
            from google_calendar_write import create_booking as _create
            from datetime import datetime
            ev = _create(
                client_name = params.get("client_name", ""),
                event_type  = params.get("event_type", "Event"),
                rooms       = params.get("rooms", ["gallery"]),
                start_dt    = datetime.fromisoformat(params["start"]),
                end_dt      = datetime.fromisoformat(params["end"]),
                guest_count = params.get("guests", 0),
                email       = params.get("email", ""),
                phone       = params.get("phone", ""),
                notes       = params.get("notes", ""),
            )
            return jsonify({"result": "Created ✓", "event_id": ev["id"], "link": ev.get("htmlLink")}), 200, _cors_headers()

        else:
            return jsonify({"error": f"Unknown command: {command}"}), 400, _cors_headers()

    except Exception as e:
        return jsonify({"error": str(e)}), 500, _cors_headers()


@chat_bp.route("/chat/reset", methods=["POST", "OPTIONS"])
def reset():
    if request.method == "OPTIONS":
        return "", 200, _cors_headers()
    data       = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    if session_id and session_id in sessions:
        sessions[session_id]      = []
        session_states[session_id] = {}
        session_meta[session_id]   = {}
    return jsonify({"status": "reset", "session_id": session_id}), 200, _cors_headers()
