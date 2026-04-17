"""
chat_backend.py
---------------
Flask blueprint powering the Sauvage booking chatbot.
Calls the Anthropic API with the full system prompt and maintains
per-session conversation history in a SQLite database so state
survives server restarts and works across gunicorn workers.

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
import sqlite3
import threading
from contextlib import contextmanager
from flask import Blueprint, request, jsonify
from typing import Optional
import anthropic

# ── Blueprint ─────────────────────────────────────────────────────────────────
chat_bp = Blueprint("chat", __name__)

# ── Anthropic client ──────────────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── SQLite session store ───────────────────────────────────────────────────────
# Persists across server restarts and gunicorn worker recycling.
_DB_PATH = os.path.join(os.path.dirname(__file__), "sessions.db")
_db_local = threading.local()

@contextmanager
def _db():
    """Return a per-thread SQLite connection (thread-safe)."""
    if not getattr(_db_local, "conn", None):
        _db_local.conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _db_local.conn.row_factory = sqlite3.Row
    yield _db_local.conn

def _init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                messages   TEXT NOT NULL DEFAULT '[]',
                state      TEXT NOT NULL DEFAULT '{}',
                meta       TEXT NOT NULL DEFAULT '{}',
                updated_at REAL NOT NULL DEFAULT (unixepoch())
            )
        """)
        conn.commit()

_init_db()

def _purge_old_sessions():
    """Delete sessions not updated in the last 7 days — run once at startup."""
    try:
        with _db() as conn:
            deleted = conn.execute(
                "DELETE FROM sessions WHERE updated_at < unixepoch() - 604800"
            ).rowcount
            conn.commit()
        if deleted:
            print(f"[Sessions] Purged {deleted} expired session(s)")
    except Exception as e:
        print(f"[Sessions] Purge error: {e}")

threading.Thread(target=_purge_old_sessions, daemon=True).start()

# ── Per-session locks (prevent background thread race on state updates) ────────
_session_locks: dict = {}
_session_locks_lock = threading.Lock()

def _get_session_lock(session_id: str) -> threading.Lock:
    with _session_locks_lock:
        if session_id not in _session_locks:
            _session_locks[session_id] = threading.Lock()
        return _session_locks[session_id]

# ── Session helpers ────────────────────────────────────────────────────────────

def _session_get(session_id: str) -> Optional[dict]:
    with _db() as conn:
        row = conn.execute(
            "SELECT messages, state, meta FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
    if row is None:
        return None
    return {
        "messages": json.loads(row["messages"]),
        "state":    json.loads(row["state"]),
        "meta":     json.loads(row["meta"]),
    }

def _session_create(session_id: str, messages: list, state: dict = None, meta: dict = None):
    with _db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO sessions (session_id, messages, state, meta, updated_at)
               VALUES (?, ?, ?, ?, unixepoch())""",
            (session_id, json.dumps(messages), json.dumps(state or {}), json.dumps(meta or {}))
        )
        conn.commit()

def _session_update(session_id: str, messages: list = None, state: dict = None, meta: dict = None):
    sets, vals = [], []
    if messages is not None:
        sets.append("messages = ?"); vals.append(json.dumps(messages))
    if state is not None:
        sets.append("state = ?");    vals.append(json.dumps(state))
    if meta is not None:
        sets.append("meta = ?");     vals.append(json.dumps(meta))
    if not sets:
        return
    sets.append("updated_at = unixepoch()")
    vals.append(session_id)
    with _db() as conn:
        conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE session_id = ?", vals)
        conn.commit()

def _session_delete(session_id: str):
    with _db() as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()

# ── Static deposit URLs (used by the bot, replaced with dynamic links) ────────
DEPOSIT_URL_STD = "https://www.selectionsauvage.nl/products/event-deposit"
DEPOSIT_URL_KIT = "https://www.selectionsauvage.nl/products/event-deposit-copy"

# ── Optional integrations (graceful degradation if not configured) ────────────
_AIRTABLE_ENABLED = False
_SHOPIFY_ENABLED  = False

# send_confirmation_email removed — replaced by confirmation_email.send_booking_confirmation

try:
    from airtable_client import (
        create_inquiry, update_inquiry, mark_deposit_pending,
        get_inquiry_by_session, confirm_booking,
    )
    _AIRTABLE_ENABLED = bool(os.getenv("AIRTABLE_API_KEY"))
    print(f"[Airtable] {'Enabled ✓' if _AIRTABLE_ENABLED else 'DISABLED — AIRTABLE_API_KEY not set'}")
except ImportError as e:
    print(f"[Airtable] Import failed: {e}")

try:
    from shopify_client import create_checkout_session as _shopify_create_checkout
    _SHOPIFY_ENABLED = bool(os.getenv("SHOPIFY_ADMIN_API_TOKEN"))
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
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "chatbot-prompt-v2.md")
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
    "event_type":         "Event type",
    "dates":              "Date(s)",
    "start_time":         "Start time",
    "end_time":           "End time",
    "is_multi_day":       "Multi-day / continuous event",
    "client_name":        "Client name",
    "email":              "Email",
    "phone":              "Phone / WhatsApp",
    "guest_count":        "Guest count",
    "customer_type":      "Booking type (private or business)",
    "rooms":              "Rooms selected",
    "duration":           "Duration (Hourly / Half-Day / Full-Day)",
    "hours":              "Number of hours (if hourly)",
    "addons":             "Add-ons confirmed",
    "quote_total":        "Quote total (incl VAT)",
    "community_pricing":  "Community pricing mode",
    "referral_source":    "How they heard about us",
    "attributed_host":    "Attributed host (Greg/Dorian/Bart/Unattributed)",
    "referred_by":        "Referred by (person name, if mentioned)",
    "arrival_time":       "Setup arrival time",
    "tandc_accepted":     "Terms of Use accepted this session",
    "payment_confirmed":  "Deposit payment confirmed — booking is locked in",
}

_EXTRACT_SYSTEM = (
    "You are a data extraction assistant. Given a booking conversation, extract ONLY "
    "facts that have been clearly confirmed by the client or stated by the bot as agreed. "
    "Return a single JSON object with these keys (omit any that are not yet confirmed):\n"
    "  event_type, dates, start_time, end_time, is_multi_day, client_name, email, phone,\n"
    "  guest_count, customer_type, rooms, duration, hours, addons, quote_total,\n"
    "  community_pricing, referral_source, attributed_host, referred_by.\n"
    "Rules:\n"
    "- event_type: one of Dinner, Birthday, Corporate, Community, Pop-up, Art Gallery, Wine Tasting, Workshop, Wedding, Other\n"
    "- dates: ISO format YYYY-MM-DD, e.g. '2026-05-10'. Current year is 2026 unless the client specifies otherwise.\n"
    "- rooms: JSON array of room names, e.g. [\"Upstairs (Gallery)\", \"Entrance\"]\n"
    "- duration: 'Hourly', 'Half-Day', or 'Full-Day'\n"
    "- hours: integer, only if duration is Hourly\n"
    "- addons: JSON array of confirmed add-on names, e.g. [\"Stemless glassware\", \"Staff 2hr\"]\n"
    "- quote_total: numeric EUR amount incl VAT if the bot has stated a total, e.g. 194.40\n"
    "- community_pricing: true if the community pricing code was used, else omit\n"
    "- arrival_time: setup arrival time stated by the client after payment confirmation, "
    "e.g. '14:00'. Only set if client explicitly said what time they will arrive.\n"
    "- referral_source: channel or person given in response to 'how did you hear about Sauvage?' "
    "e.g. 'Instagram', 'Google', 'Organic', 'Greg', 'Dorian', 'Bart', 'Other'\n"
    "- attributed_host: 'Greg', 'Dorian', or 'Bart' if a host was named; otherwise 'Unattributed'. "
    "Only set this if the client answered the attribution question.\n"
    "- referred_by: the specific person who referred them, verbatim — only if a person was named "
    "(e.g. 'I heard from Greg' → referred_by: 'Greg'). Omit if just a channel was given.\n"
    "- customer_type: 'Private' if client said private/personal, 'Business' if corporate/company/business. "
    "Look for words like 'private', 'personal', 'business', 'corporate', 'company' anywhere in the conversation.\n"
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
            max_tokens=500,
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

def _ensure_airtable_record(session_id: str, state: dict, meta: dict) -> Optional[str]:
    """Create an Airtable inquiry record the first time we have an event type.
    Re-reads from DB right before creating to avoid double-creation race condition
    between concurrent gunicorn workers."""
    if not _AIRTABLE_ENABLED:
        return None
    if "record_id" not in meta and state.get("event_type"):
        # Re-read meta from DB — another worker may have already created the record
        fresh = _session_get(session_id)
        if fresh and fresh["meta"].get("record_id"):
            meta["record_id"] = fresh["meta"]["record_id"]
            return meta["record_id"]
        try:
            record_id = create_inquiry(session_id, _clean_str(state["event_type"]))
            meta["record_id"] = record_id
            _session_update(session_id, meta=meta)
            print(f"Airtable inquiry created: {record_id} for session {session_id}")
        except Exception as e:
            print(f"Airtable create_inquiry error: {e}")
    return meta.get("record_id")

_FUNNEL_STAGE_ORDER = [
    "1_event_type", "2_date_time", "3_contact",
    "4_rooms", "5_addons", "6_quoted",
    "7_deposit_pending", "8_confirmed",
]

def _infer_funnel_stage(state: dict) -> str:
    if state.get("quote_total"):
        return "6_quoted"
    if state.get("addons"):
        return "5_addons"
    if state.get("rooms"):
        return "4_rooms"
    if state.get("client_name") or state.get("email"):
        return "3_contact"
    if state.get("dates") or state.get("start_time") or state.get("end_time"):
        return "2_date_time"
    return "1_event_type"

def _clean_str(val) -> str:
    """Strip surrounding quotes that the LLM sometimes adds."""
    if isinstance(val, str):
        return val.strip().strip('"').strip("'")
    return val

def _to_int(val) -> Optional[int]:
    """Extract first integer from a value like '20' or '20 people'."""
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    m = re.search(r'\d+', str(val))
    return int(m.group()) if m else None

def _to_float(val) -> Optional[float]:
    """Extract a float from a value like '194.40' or '€194.40'."""
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r'[\d]+\.?\d*', str(val).replace(',', '.'))
    return float(m.group()) if m else None

def _sync_airtable(session_id: str, state: dict, meta: dict) -> None:
    """Push all confirmed fields to Airtable and advance funnel stage."""
    if not _AIRTABLE_ENABLED:
        return
    record_id = _ensure_airtable_record(session_id, state, meta)
    if not record_id:
        return
    last = meta.get("last_pushed", {})

    updates = {}

    # String scalar fields
    str_map = {
        "event_type":     "Event Type",
        "client_name":    "Client Name",
        "email":          "Email",
        "phone":          "Phone",
        "customer_type":  "Customer Type",
        # "is_multi_day" has no Airtable column — captured implicitly in Requested Date
        "duration":       "Duration",
        "arrival_time":   "Arrival Time",
    }
    for key, at_field in str_map.items():
        val = state.get(key)
        if val and val != last.get(key):
            updates[at_field] = _clean_str(val)

    # Attribution — push all three fields together when referral_source is first seen
    _HOST_NAMES = {"greg", "dorian", "bart"}
    ref_src = state.get("referral_source")
    # Skip if already pushed deterministically via [ref:] widget tag
    if ref_src and not last.get("referral_direct_pushed") and ref_src != last.get("referral_source"):
        cleaned_src = _clean_str(ref_src)
        updates["Referral Source"] = cleaned_src
        # Derive attributed host: person > channel
        explicit_host = _clean_str(state.get("attributed_host", ""))
        if explicit_host and explicit_host.lower() not in ("unattributed", ""):
            updates["Attributed Host"] = explicit_host
        elif cleaned_src.lower() in _HOST_NAMES:
            updates["Attributed Host"] = cleaned_src.capitalize()
        else:
            updates["Attributed Host"] = "Unattributed"
        # Referred By — specific person if named
        ref_by = state.get("referred_by") or (
            cleaned_src if cleaned_src.lower() in _HOST_NAMES else None
        )
        if ref_by:
            updates["Referred By"] = _clean_str(ref_by)

    # Requested Date — Airtable only accepts a single ISO date string.
    # If the LLM extracted a list (multi-day booking), use the first date.
    dates_val = state.get("dates")
    if dates_val and dates_val != last.get("dates"):
        if isinstance(dates_val, list):
            first_date = _clean_str(dates_val[0]) if dates_val else None
        else:
            first_date = _clean_str(str(dates_val))
        # Validate it looks like an ISO date before sending
        if first_date and re.match(r'^\d{4}-\d{2}-\d{2}$', first_date):
            updates["Requested Date"] = first_date

    # Guest Count — must be an integer
    gc = state.get("guest_count")
    if gc and gc != last.get("guest_count"):
        parsed = _to_int(gc)
        if parsed is not None:
            updates["Guest Count"] = parsed

    # Hours — must be an integer
    hrs = state.get("hours")
    if hrs and hrs != last.get("hours"):
        parsed = _to_int(hrs)
        if parsed is not None:
            updates["Hours"] = parsed

    # Quote total — derive all three VAT fields from incl-VAT (rate is fixed at 21%)
    qt = state.get("quote_total")
    if qt and qt != last.get("quote_total"):
        incl_vat = _to_float(qt)
        if incl_vat is not None:
            ex_vat     = round(incl_vat / 1.21, 2)
            vat_amount = round(incl_vat - ex_vat, 2)
            updates["Total Incl VAT"] = incl_vat
            updates["Total Ex VAT"]   = ex_vat
            updates["VAT Amount"]     = vat_amount
            deposit = 50.0 if not (state.get("rooms") and "Kitchen" in str(state.get("rooms", []))) else 300.0
            updates["Deposit Amount Due"] = deposit
            print(f"[Airtable] Quote sync: €{incl_vat} incl VAT, deposit €{deposit}")

    # Time Slot — combine start + end into "HH:MM-HH:MM"
    start = state.get("start_time")
    end   = state.get("end_time")
    if start and (start != last.get("start_time") or end != last.get("end_time")):
        slot = f"{_clean_str(start)}-{_clean_str(end)}" if end else _clean_str(start)
        updates["Time Slot"] = slot

    # Room name normalisation — map LLM shorthand → exact Airtable select options
    _ROOM_MAP = {
        "upstairs":           "Upstairs (Gallery)",
        "gallery":            "Upstairs (Gallery)",
        "upstairs (gallery)": "Upstairs (Gallery)",
        "entrance":           "Entrance",
        "front":              "Entrance",
        "bar":                "Entrance",
        "kitchen":            "Kitchen",
        "cave":               "Cave",
        "wine cave":          "Cave",
    }

    def _normalise_rooms(raw) -> list:
        items = raw if isinstance(raw, list) else [raw]
        result = []
        for item in items:
            cleaned = _clean_str(item).lower()
            result.append(_ROOM_MAP.get(cleaned, _clean_str(item)))
        return result

    def _clean_list(raw) -> list:
        items = raw if isinstance(raw, list) else [raw]
        return [_clean_str(i) for i in items if i]

    # Multi-select fields
    rooms = state.get("rooms")
    if rooms and rooms != last.get("rooms"):
        updates["Rooms Requested"] = _normalise_rooms(rooms)

    addons = state.get("addons")
    # Skip if already pushed deterministically via [at:] widget tag — LLM names won't match
    if addons and not last.get("addons_direct_pushed"):
        updates["Add-Ons"] = _clean_list(addons)

    # Community pricing flag
    if state.get("community_pricing") and not last.get("community_pricing"):
        updates["Community Pricing"] = True

    # Funnel stage — advance forward only, never backward
    new_stage  = _infer_funnel_stage(state)
    last_stage = last.get("funnel_stage", "1_event_type")
    if _FUNNEL_STAGE_ORDER.index(new_stage) > _FUNNEL_STAGE_ORDER.index(last_stage):
        updates["Funnel Stage"] = new_stage

    if updates:
        try:
            update_inquiry(record_id, updates)
            # Persist what we've pushed so we don't re-push unchanged fields
            new_last = {**last, **{k: state[k] for k in state if state.get(k)}}
            new_last["funnel_stage"] = new_stage if "Funnel Stage" in updates else last_stage
            meta["last_pushed"] = new_last
            _session_update(session_id, meta=meta)
        except Exception as e:
            print(f"Airtable sync error: {e}")

# ── Shopify checkout injection ────────────────────────────────────────────────

def _inject_checkout_url(session_id: str, state: dict, meta: dict, bot_response: str) -> str:
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

    record_id = _ensure_airtable_record(session_id, state, meta)
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
        _session_update(session_id, meta=meta)

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

# ── Widget hint ───────────────────────────────────────────────────────────────

def _determine_widget(state: dict, bot_text: str, sent_widgets: list) -> Optional[str]:
    """
    Tell the frontend which interactive widget to show next.
    This is the authoritative signal — far more reliable than client-side text matching.
    Returns a widget key or None.

    sent_widgets: list of widget keys already shown this session (from meta["widgets_sent"]).
    Each one-shot widget (addons, contact, customer_type, attribution, tandc) fires at most once.
    """
    t = bot_text.lower()

    def _once(key: str) -> Optional[str]:
        """Return key only if it hasn't been sent yet this session."""
        return key if key not in sent_widgets else None

    # Date/time picker — can show multiple times (different question)
    if "select your dates" in t or "select a date" in t:
        return "datetime"

    # Contact form — only if we're genuinely missing at least one contact field
    has_all_contact = state.get("client_name") and state.get("email") and state.get("phone")
    if not has_all_contact:
        contact_triggers = [
            "what's your name", "your name?", "best email",
            "reach you on", "how can we reach",
            "name and contact", "contact details",
        ]
        if any(tr in t for tr in contact_triggers):
            return _once("contact")
        if "name" in t and any(w in t for w in ["email", "phone", "reach", "whatsapp"]):
            return _once("contact")

    # Customer type — only if still unknown
    if not state.get("customer_type"):
        ctype_triggers = [
            "private booking or", "is this a private",
            "private or business", "personal or business",
            "individual or business", "booking as a",
        ]
        if any(tr in t for tr in ctype_triggers) or ("private" in t and "business" in t):
            return _once("customer_type")

    # Add-ons — exact trigger phrase only; fires at most once per session
    if "add-ons for your event" in t and ("select" in t or "include" in t or "available" in t):
        return _once("addons")

    # Attribution / referral
    if "hear about" in t or "referred" in t or "find us" in t or "how did you" in t:
        return _once("attribution")

    # T&C acceptance — fires at most once per session
    if "terms of use" in t or ("terms" in t and ("sauvage.amsterdam/terms" in t or "accept" in t or "confirm" in t)):
        return _once("tandc")

    return None


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
    _session_create(session_id, [{"role": "assistant", "content": GREETING}])
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
    if len(message) > 2000:
        return jsonify({"error": "Message too long (max 2000 characters)"}), 400, _cors_headers()

    sess = _session_get(session_id) if session_id else None
    if sess is None:
        session_id = session_id or str(uuid.uuid4())
        _session_create(session_id, [])
        sess = {"messages": [], "state": {}, "meta": {}}

    # ── Deterministic addon sync ──────────────────────────────────────────────
    # The widget embeds [at:Value1,Value2] in the submission message.
    # Parse and push directly to Airtable — no LLM extraction needed.
    if "add-ons" in message.lower() or "[at:" in message.lower():
        print(f"[Addons] Raw incoming message: {repr(message)}")
    _at_addons = []
    _at_match = re.search(r'\[at:([^\]]*)\]', message)
    if _at_match:
        raw = _at_match.group(1).strip()
        _at_addons = [v.strip() for v in raw.split(",") if v.strip()]
        # Strip the tag so Claude never sees it
        message = (message[:_at_match.start()] + message[_at_match.end():]).strip()

    # ── Deterministic referral source sync ───────────────────────────────────
    # The attribution widget embeds [ref:Value] — push directly to Airtable.
    _ref_value = None
    _ref_match = re.search(r'\[ref:([^\]]*)\]', message)
    if _ref_match:
        _ref_value = _ref_match.group(1).strip()
        message = (message[:_ref_match.start()] + message[_ref_match.end():]).strip()

    # ── Track T&C acceptance ──────────────────────────────────────────────────
    if "accepted the terms of use" in message.lower() or "i have read and accepted" in message.lower():
        sess["meta"]["tandc_accepted"] = True
        _session_update(session_id, meta=sess["meta"])

    messages = sess["messages"]
    messages.append({"role": "user", "content": message})

    # Push addon list to Airtable immediately (synchronous, before LLM call)
    if _at_addons and _AIRTABLE_ENABLED:
        _r_id = sess["meta"].get("record_id")
        if _r_id:
            try:
                from airtable_client import update_inquiry as _upd_at
                _upd_at(_r_id, {"Add-Ons": _at_addons})
                # Mark in meta so _sync_airtable doesn't re-push with LLM values
                sess["meta"].setdefault("last_pushed", {})["addons"] = _at_addons
                sess["meta"]["last_pushed"]["addons_direct_pushed"] = True
                _session_update(session_id, meta=sess["meta"])
                print(f"[Addons] Direct sync → {_at_addons}")
            except Exception as _e:
                print(f"[Addons] Direct sync error: {_e}")

    # Push referral source to Airtable immediately
    _HOST_NAMES_SET = {"greg", "dorian", "bart"}
    if _ref_value and _AIRTABLE_ENABLED:
        _r_id = sess["meta"].get("record_id")
        if _r_id:
            try:
                from airtable_client import update_inquiry as _upd_at
                _ref_fields = {"Referral Source": _ref_value}
                if _ref_value.lower() in _HOST_NAMES_SET:
                    _ref_fields["Attributed Host"] = _ref_value.capitalize()
                    _ref_fields["Referred By"]     = _ref_value.capitalize()
                else:
                    _ref_fields["Attributed Host"] = "Unattributed"
                _upd_at(_r_id, _ref_fields)
                sess["meta"].setdefault("last_pushed", {})["referral"] = _ref_value
                sess["meta"]["last_pushed"]["referral_direct_pushed"] = True
                _session_update(session_id, meta=sess["meta"])
                print(f"[Referral] Direct sync → {_ref_fields}")
            except Exception as _e:
                print(f"[Referral] Direct sync error: {_e}")
    history = messages[-20:]   # keep last 10 exchanges — ~3-4K tokens, much faster

    # Use state already accumulated from previous turns — no blocking LLM call needed now.
    # A background thread will extract new state after we return the response.
    state = dict(sess["state"])
    meta  = sess["meta"]

    # Inject T&C acceptance and payment flags into state so Claude sees them
    if meta.get("tandc_accepted"):
        state["tandc_accepted"] = True
    if meta.get("payment_confirmed"):
        state["payment_confirmed"] = True

    # Fast regex pre-pass — catch customer_type directly from the raw message
    # so the bot never re-asks even if the LLM extractor missed it
    if not state.get("customer_type"):
        msg_lower = message.lower()
        if any(w in msg_lower for w in ["private", "personal", "privé"]):
            state["customer_type"] = "Private"
        elif any(w in msg_lower for w in ["business", "corporate", "company", "zakelijk", "btw"]):
            state["customer_type"] = "Business"

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

    assistant_text = None
    for _attempt in range(3):
        try:
            response = client.messages.create(
                model      = "claude-haiku-4-5-20251001",
                max_tokens = 2048,
                system     = full_system,
                messages   = history,
            )
            assistant_text = response.content[0].text
            break
        except Exception as e:
            _err_str = str(e)
            if "529" in _err_str or "overloaded" in _err_str.lower():
                if _attempt < 2:
                    import time; time.sleep(2 * (_attempt + 1))
                    continue
            # Non-retryable or exhausted retries — return 200 so widget shows fallback
            print(f"Anthropic API error: {_err_str}")
            return jsonify({"error": _err_str}), 200, _cors_headers()
    if assistant_text is None:
        return jsonify({"error": "Service temporarily overloaded, please try again in a moment."}), 200, _cors_headers()

    # Replace static deposit URL with a session-linked Shopify checkout URL
    try:
        assistant_text = _inject_checkout_url(session_id, state, meta, assistant_text)
    except Exception as e:
        print(f"_inject_checkout_url error: {e}")

    messages.append({"role": "assistant", "content": assistant_text})
    _session_update(session_id, messages=messages, state=state, meta=meta)

    # Background: extract state from this exchange and sync to Airtable.
    # Uses a per-session lock so concurrent messages don't race on state.
    def _background_update(sid, hist, cur_meta):
        lock = _get_session_lock(sid)
        with lock:
            try:
                new_state = _extract_booking_state(hist)
                # Re-read the latest state from DB to avoid stale overwrites
                latest_sess = _session_get(sid)
                base_state = latest_sess["state"] if latest_sess else {}
                merged = {**base_state, **new_state} if new_state else base_state
                # Regex pre-pass on last user message — catch fields the LLM often misses
                last_user = next((m["content"] for m in reversed(hist) if m["role"] == "user"), "")
                msg_lower = last_user.lower()
                # Regex pass on last assistant message — reliably extract quote_total
                last_asst = next((m["content"] for m in reversed(hist) if m["role"] == "assistant"), "")
                if not merged.get("quote_total"):
                    # Match "Total incl VAT: €1 234,56" or "Total incl VAT: €1234.56"
                    _qt_match = re.search(
                        r"total\s+incl\.?\s+vat[:\s]+€\s*([\d\s,\.]+)",
                        last_asst, re.IGNORECASE
                    )
                    if _qt_match:
                        raw_num = _qt_match.group(1).strip().replace(" ", "").replace(",", ".")
                        # Handle "1.234.56" → take last dot as decimal
                        parts = raw_num.split(".")
                        if len(parts) > 2:
                            raw_num = "".join(parts[:-1]).replace(".", "") + "." + parts[-1]
                        try:
                            merged["quote_total"] = float(raw_num)
                            print(f"[BG] Regex-extracted quote_total: {merged['quote_total']}")
                        except ValueError:
                            pass
                if not merged.get("customer_type"):
                    if any(w in msg_lower for w in ["private", "personal", "priv\u00e9"]):
                        merged["customer_type"] = "Private"
                    elif any(w in msg_lower for w in ["business", "corporate", "company", "zakelijk", "btw"]):
                        merged["customer_type"] = "Business"
                # Arrival time — widget sends "I'll arrive at HH:MM for setup."
                if not merged.get("arrival_time"):
                    _arr = re.search(r"\barrive\b.*?(\d{1,2}:\d{2})", msg_lower)
                    if not _arr:
                        _arr = re.search(r"(\d{1,2}:\d{2}).*?\bsetup\b", msg_lower)
                    if not _arr:
                        _arr = re.search(r"\barrival\b.*?(\d{1,2}:\d{2})", msg_lower)
                    if _arr:
                        merged["arrival_time"] = _arr.group(1)
                if merged != base_state:
                    _session_update(sid, state=merged)
                cur_state = merged
            except Exception as e:
                print(f"Background extraction error: {e}")
                latest_sess = _session_get(sid)
                cur_state = latest_sess["state"] if latest_sess else {}
            try:
                latest_meta = _session_get(sid)["meta"] if _session_get(sid) else cur_meta
                _sync_airtable(sid, cur_state, latest_meta)
            except Exception as e:
                print(f"Background Airtable sync error: {e}")

    threading.Thread(
        target=_background_update,
        args=(session_id, list(messages), dict(meta)),
        daemon=True,
    ).start()

    sent_widgets = meta.get("widgets_sent", [])
    widget_hint  = _determine_widget(state, assistant_text, sent_widgets)

    # Track which one-shot widgets have been sent so we never fire them twice
    if widget_hint and widget_hint != "datetime":
        if widget_hint not in sent_widgets:
            meta["widgets_sent"] = sent_widgets + [widget_hint]
            _session_update(session_id, meta=meta)

    resp = {
        "session_id":    session_id,
        "response":      assistant_text,
        "message_count": len(messages),
    }
    if widget_hint:
        resp["widget"] = widget_hint

    # If addons widget is being shown, check if Fento was mentioned earlier — pre-select it
    if widget_hint == "addons":
        fento_preselect = None
        # Check LLM-extracted addons state first
        extracted_addons = [str(a).lower() for a in (state.get("addons") or [])]
        if any("light" in a and "fento" in a for a in extracted_addons):
            fento_preselect = "light-snacks"
        elif any("snack" in a and "fento" in a for a in extracted_addons) or any("fento" in a for a in extracted_addons):
            fento_preselect = "snacks"
        # Fallback: scan recent conversation for Fento mentions
        if not fento_preselect:
            recent_text = " ".join(
                m["content"].lower() for m in messages[-6:]
                if m.get("role") == "user"
            )
            if "fento" in recent_text:
                if "light" in recent_text:
                    fento_preselect = "light-snacks"
                else:
                    fento_preselect = "snacks"
        if fento_preselect:
            pax = state.get("guest_count")
            try:
                pax = int(pax) if pax else 10
            except (ValueError, TypeError):
                pax = 10
            resp["widget_data"] = {"preselect": [fento_preselect], "pax": pax}
            print(f"[Widget] Addons pre-select: {fento_preselect} × {pax} pax")

    return jsonify(resp), 200, _cors_headers()


@chat_bp.route("/chat/payment-status/<session_id>", methods=["GET", "OPTIONS"])
def payment_status(session_id):
    """
    Widget polls this endpoint after the payment link is shown.
    Returns {"status": "pending"|"confirmed"|"unknown"}.
    Checks Airtable as the source of truth — the Shopify webhook updates it on payment.
    """
    if request.method == "OPTIONS":
        return "", 200, _cors_headers()

    sess   = _session_get(session_id)
    meta   = sess["meta"] if sess else {}
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
                    # Send branded confirmation email via confirmation_email.py
                    if not meta.get("confirmation_email_sent"):
                        try:
                            from confirmation_email import send_booking_confirmation
                            state = (sess or {}).get("state", {})
                            send_booking_confirmation(meta.get("record_id"), state)
                            meta["confirmation_email_sent"] = True
                            _session_update(session_id, meta=meta)
                        except Exception as _e:
                            print(f"[Email] payment_status confirmation failed: {_e}")
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

    sess      = _session_get(session_id)
    meta      = sess["meta"] if sess else {}
    record_id = meta.get("record_id")

    state = (sess or {}).get("state", {})

    if record_id and _AIRTABLE_ENABLED:
        try:
            confirm_booking(record_id)
        except Exception as e:
            return jsonify({"error": str(e)}), 500, _cors_headers()
    else:
        # Airtable not wired — persist the flag so poll endpoint returns confirmed
        meta["_test_confirmed"] = True

    # Mark payment as confirmed in session so Claude stops showing deposit link
    meta["payment_confirmed"] = True
    if sess:
        _session_update(session_id, meta=meta)
    else:
        _session_create(session_id, [], meta=meta)

    # Create Google Calendar event for the test booking
    try:
        import importlib
        _wh = importlib.import_module("shopify_webhook")
        if _wh._GCAL_WRITE:
            start = _wh._build_dt(state.get("dates"), state.get("start_time", ""))
            end   = _wh._build_dt(state.get("dates"), state.get("end_time",   ""))
            if start and end:
                rooms = state.get("rooms") or []
                if isinstance(rooms, str):
                    rooms = [rooms]
                cal_event = _wh._gcal_create(
                    client_name = state.get("client_name", "Test"),
                    event_type  = state.get("event_type", "Event"),
                    rooms       = rooms,
                    start_dt    = start,
                    end_dt      = end,
                    guest_count = state.get("guest_count", 0),
                    email       = state.get("email", ""),
                    phone       = state.get("phone", ""),
                    airtable_id = record_id or "test",
                )
                cal_link = cal_event.get("htmlLink", "")
                print(f"[test-confirm] Calendar event created: {cal_link}")
                if record_id and _AIRTABLE_ENABLED:
                    from airtable_client import update_inquiry as _upd
                    _upd(record_id, {"Notes": f"Google Calendar event: {cal_link}"})
            else:
                print(f"[test-confirm] Skipped calendar — missing dates/times in state")
    except Exception as e:
        print(f"[test-confirm] Calendar creation failed: {e}")

    # Fire Make.com notification
    try:
        import importlib as _il
        _wh2 = _il.import_module("shopify_webhook")
        _wh2._notify_make({
            "event":        "booking_confirmed",
            "order_number": "TEST",
            "airtable_id":  record_id or "none",
            "client_name":  state.get("client_name", "Test"),
            "client_email": state.get("email", ""),
            "client_phone": state.get("phone", ""),
            "event_type":   state.get("event_type", ""),
            "event_date":   str(state.get("dates", "")),
            "start_time":   state.get("start_time", ""),
            "end_time":     state.get("end_time", ""),
            "guest_count":  state.get("guest_count", ""),
            "rooms":        state.get("rooms", []),
            "deposit_amount": "TEST",
            "source":       "test-confirm",
        })
    except Exception as e:
        print(f"[test-confirm] Make.com notification failed: {e}")

    # Send booking confirmation email
    try:
        from confirmation_email import send_booking_confirmation
        if record_id:
            send_booking_confirmation(record_id, state)
        else:
            print("[test-confirm] Skipped confirmation email — no record_id")
    except Exception as e:
        print(f"[test-confirm] Confirmation email failed: {e}")

    return jsonify({
        "status":     "confirmed",
        "session_id": session_id,
        "record_id":  record_id,
    }), 200, _cors_headers()


# ── Arrival time form ─────────────────────────────────────────────────────────

@chat_bp.route("/arrival", methods=["GET"])
def arrival_form():
    """Branded HTML form for client to confirm their arrival time."""
    record_id = request.args.get("record", "")
    token     = request.args.get("token", "")

    try:
        from confirmation_email import verify_arrival_token
        valid = verify_arrival_token(record_id, token)
    except Exception:
        valid = False

    if not valid or not record_id:
        return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Invalid Link — Sauvage</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;background:#f5f3ef;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}
.box{background:#fff;padding:48px;border-radius:4px;max-width:400px;text-align:center;}
h1{font-size:20px;font-weight:500;color:#1a1a1a;margin:0 0 12px;}
p{color:#666;font-size:14px;line-height:1.6;margin:0;}</style></head>
<body><div class="box">
<h1>Link not valid</h1>
<p>This arrival link has expired or is invalid. Please contact Greg on
<a href="https://wa.me/31634742988" style="color:#1a1a1a;">WhatsApp</a>
or <a href="tel:+31634742988" style="color:#1a1a1a;">+31 634 742 988</a>.</p>
</div></body></html>""", 400

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Confirm Arrival — Sauvage</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
      background: #f5f3ef;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    .card {{
      background: #ffffff;
      border-radius: 4px;
      overflow: hidden;
      width: 100%;
      max-width: 480px;
    }}
    .header {{
      background: #1a1a1a;
      padding: 28px 32px;
    }}
    .header span {{
      display: block;
      font-size: 11px;
      letter-spacing: 3px;
      text-transform: uppercase;
      color: #888;
      margin-bottom: 6px;
    }}
    .header h1 {{
      font-size: 22px;
      font-weight: 400;
      color: #ffffff;
      letter-spacing: -0.3px;
    }}
    .body {{
      padding: 32px;
    }}
    p {{
      font-size: 15px;
      line-height: 1.7;
      color: #333;
      margin-bottom: 24px;
    }}
    label {{
      display: block;
      font-size: 11px;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      color: #999;
      margin-bottom: 8px;
      font-weight: 600;
    }}
    input[type="time"] {{
      width: 100%;
      padding: 12px 14px;
      font-size: 16px;
      border: 1px solid #ddd;
      border-radius: 3px;
      background: #fafafa;
      color: #1a1a1a;
      margin-bottom: 24px;
      -webkit-appearance: none;
    }}
    button {{
      width: 100%;
      background: #1a1a1a;
      color: #ffffff;
      border: none;
      padding: 14px 28px;
      font-size: 14px;
      font-weight: 500;
      letter-spacing: 0.5px;
      border-radius: 3px;
      cursor: pointer;
    }}
    button:hover {{ background: #333; }}
    .footer {{
      background: #1a1a1a;
      padding: 16px 32px;
      font-size: 12px;
      color: #666;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <span>Sauvage Amsterdam</span>
      <h1>When will you arrive?</h1>
    </div>
    <div class="body">
      <p>Let us know what time you're planning to arrive for setup — this helps us coordinate with the other residents sharing the building.</p>
      <form method="POST" action="/arrival">
        <input type="hidden" name="record" value="{record_id}">
        <input type="hidden" name="token"  value="{token}">
        <label for="arrival_time">Arrival time</label>
        <input type="time" id="arrival_time" name="arrival_time" required>
        <button type="submit">Confirm arrival time →</button>
      </form>
    </div>
    <div class="footer">
      Sauvage · Potgieterstraat 47H · Amsterdam ·
      <a href="https://sauvage.amsterdam" style="color:#888;text-decoration:none;">sauvage.amsterdam</a>
    </div>
  </div>
</body>
</html>"""


@chat_bp.route("/arrival", methods=["POST"])
def arrival_submit():
    """Receive arrival time form submission and write to Airtable."""
    record_id    = request.form.get("record", "")
    token        = request.form.get("token", "")
    arrival_time = request.form.get("arrival_time", "").strip()

    try:
        from confirmation_email import verify_arrival_token
        valid = verify_arrival_token(record_id, token)
    except Exception:
        valid = False

    if not valid or not record_id or not arrival_time:
        return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Error — Sauvage</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;background:#f5f3ef;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}
.box{background:#fff;padding:48px;border-radius:4px;max-width:400px;text-align:center;}
h1{font-size:20px;font-weight:500;color:#1a1a1a;margin:0 0 12px;}
p{color:#666;font-size:14px;line-height:1.6;margin:0;}</style></head>
<body><div class="box">
<h1>Something went wrong</h1>
<p>Please go back and try again, or contact Greg on
<a href="https://wa.me/31634742988" style="color:#1a1a1a;">WhatsApp</a>
or <a href="tel:+31634742988" style="color:#1a1a1a;">+31 634 742 988</a>.</p>
</div></body></html>""", 400

    # Save to Airtable
    try:
        from airtable_client import update_inquiry
        update_inquiry(record_id, {"Arrival Time": arrival_time})
        print(f"[Arrival] Saved {arrival_time} for record {record_id}")
    except Exception as e:
        print(f"[Arrival] Airtable update failed: {e}")
        return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Error — Sauvage</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;background:#f5f3ef;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}
.box{background:#fff;padding:48px;border-radius:4px;max-width:400px;text-align:center;}
h1{font-size:20px;font-weight:500;color:#1a1a1a;margin:0 0 12px;}
p{color:#666;font-size:14px;line-height:1.6;margin:0;}</style></head>
<body><div class="box">
<h1>Could not save your arrival time</h1>
<p>Please contact Greg on
<a href="https://wa.me/31634742988" style="color:#1a1a1a;">WhatsApp</a>
or <a href="tel:+31634742988" style="color:#1a1a1a;">+31 634 742 988</a>.</p>
</div></body></html>""", 500

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>All set — Sauvage</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
      background: #f5f3ef;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .card {
      background: #ffffff;
      border-radius: 4px;
      overflow: hidden;
      width: 100%;
      max-width: 480px;
    }
    .header {
      background: #1a1a1a;
      padding: 28px 32px;
    }
    .header span {
      display: block;
      font-size: 11px;
      letter-spacing: 3px;
      text-transform: uppercase;
      color: #888;
      margin-bottom: 6px;
    }
    .header h1 {
      font-size: 22px;
      font-weight: 400;
      color: #ffffff;
    }
    .body {
      padding: 32px;
    }
    .check {
      font-size: 36px;
      margin-bottom: 16px;
    }
    p {
      font-size: 15px;
      line-height: 1.7;
      color: #333;
    }
    .footer {
      background: #1a1a1a;
      padding: 16px 32px;
      font-size: 12px;
      color: #666;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <span>Sauvage Amsterdam</span>
      <h1>You're all set</h1>
    </div>
    <div class="body">
      <div class="check">✓</div>
      <p>Your arrival time has been noted. We'll make sure everything is ready for you. See you soon.</p>
    </div>
    <div class="footer">
      Sauvage · Potgieterstraat 47H · Amsterdam ·
      <a href="https://sauvage.amsterdam" style="color:#888;text-decoration:none;">sauvage.amsterdam</a>
    </div>
  </div>
</body>
</html>"""


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
    if session_id:
        _session_delete(session_id)
    return jsonify({"status": "reset", "session_id": session_id}), 200, _cors_headers()
