"""
google_calendar_write.py
------------------------
Write, update, and delete events on the Sauvage reservations Google Calendar.
Uses OAuth2 with refresh token — no user interaction needed after initial auth.

Calendar: sauvagespace.reservations@gmail.com
"""

import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
CALENDAR_ID = "sauvagespace.reservations@gmail.com"

# Credentials — loaded from env or file
_CREDS_PATH = os.path.join(os.path.dirname(__file__), ".secrets", "google-calendar-credentials.json")
_TOKEN_PATH = os.path.join(os.path.dirname(__file__), ".secrets", "google-calendar-token.json")

# In-memory token cache
_token_cache: dict = {"access_token": None, "expires_at": 0}


# ── Auth ──────────────────────────────────────────────────────────────────────

def _load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _save_token(token_data: dict):
    os.makedirs(os.path.dirname(_TOKEN_PATH), exist_ok=True)
    with open(_TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)


def _get_access_token() -> str:
    """Return a valid access token, refreshing if needed."""
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    token_data = _load_json(_TOKEN_PATH)
    creds      = _load_json(_CREDS_PATH)["installed"]

    post_data = urllib.parse.urlencode({
        "refresh_token": token_data["refresh_token"],
        "client_id":     creds["client_id"],
        "client_secret": creds["client_secret"],
        "grant_type":    "refresh_token",
    }).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=post_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        new_tokens = json.loads(resp.read())

    if "error" in new_tokens:
        raise RuntimeError(f"Token refresh failed: {new_tokens}")

    # Merge and persist
    token_data.update(new_tokens)
    _save_token(token_data)

    _token_cache["access_token"] = new_tokens["access_token"]
    _token_cache["expires_at"]   = now + new_tokens.get("expires_in", 3600)

    return new_tokens["access_token"]


def _api(method: str, path: str, body: Optional[dict] = None) -> dict:
    """Make a Google Calendar API request."""
    token = _get_access_token()
    url   = f"https://www.googleapis.com/calendar/v3{path}"
    data  = json.dumps(body).encode() if body else None

    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise RuntimeError(f"Calendar API {method} {path} failed ({e.code}): {error_body}")


# ── Room title formatting ─────────────────────────────────────────────────────

def _build_title(rooms: list[str], client_name: str, event_type: str) -> str:
    """
    Build a calendar event title matching the existing convention:
    e.g. "GALLERY+ENTRANCE- Jane Smith (Birthday)"
         "KITCHEN- Maegen (Workshop)"
         "EVENT FULL SPACE- Ahmed (Corporate)"
    """
    room_labels = {
        "gallery":  "GALLERY",
        "entrance": "ENTRANCE",
        "kitchen":  "KITCHEN",
        "cave":     "CAVE",
    }
    room_parts = [room_labels.get(r, r.upper()) for r in rooms if r in room_labels]

    if set(rooms) >= {"gallery", "entrance", "kitchen", "cave"}:
        prefix = "FULL SPACE"
    elif len(room_parts) > 1:
        prefix = "+".join(room_parts)
    else:
        prefix = room_parts[0] if room_parts else "EVENT"

    return f"{prefix}- {client_name} ({event_type})"


# ── Public API ────────────────────────────────────────────────────────────────

def create_booking(
    client_name:  str,
    event_type:   str,
    rooms:        list[str],
    start_dt:     datetime,
    end_dt:       datetime,
    guest_count:  int = 0,
    email:        str = "",
    phone:        str = "",
    notes:        str = "",
    airtable_id:  str = "",
) -> dict:
    """
    Create a Google Calendar event for a confirmed booking.
    Returns the created event dict (includes 'id' and 'htmlLink').
    """
    title       = _build_title(rooms, client_name, event_type)
    description = (
        f"Client: {client_name}\n"
        f"Event: {event_type}\n"
        f"Rooms: {', '.join(r.capitalize() for r in rooms)}\n"
        f"Guests: {guest_count}\n"
    )
    if email:   description += f"Email: {email}\n"
    if phone:   description += f"Phone: {phone}\n"
    if notes:   description += f"Notes: {notes}\n"
    if airtable_id: description += f"Airtable ID: {airtable_id}\n"
    description += "\n📅 Booked via Sauvage Booking Assistant"

    event = {
        "summary":     title,
        "description": description,
        "location":    "Sauvage Space, Potgieterstraat 47H, 1053 XS Amsterdam",
        "start": {
            "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "Europe/Amsterdam",
        },
        "end": {
            "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "Europe/Amsterdam",
        },
        "colorId": _room_color(rooms),
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email",  "minutes": 1440},  # 24h before
                {"method": "popup",  "minutes": 120},   # 2h before
            ],
        },
    }

    result = _api("POST", f"/calendars/{CALENDAR_ID}/events", event)
    print(f"[Calendar] Created: {title} → {result.get('htmlLink', '')}")
    return result


def update_booking(
    event_id:    str,
    updates:     dict,
) -> dict:
    """
    Patch an existing calendar event.
    `updates` can include: summary, description, start, end, colorId.
    """
    result = _api("PATCH", f"/calendars/{CALENDAR_ID}/events/{event_id}", updates)
    print(f"[Calendar] Updated event {event_id}")
    return result


def cancel_booking(event_id: str) -> bool:
    """Delete a calendar event by ID."""
    try:
        _api("DELETE", f"/calendars/{CALENDAR_ID}/events/{event_id}")
        print(f"[Calendar] Deleted event {event_id}")
        return True
    except RuntimeError as e:
        if "404" in str(e):
            return True  # already gone
        raise


def get_event(event_id: str) -> dict:
    """Fetch a single event by ID."""
    return _api("GET", f"/calendars/{CALENDAR_ID}/events/{event_id}")


def find_events_by_name(name: str, days_ahead: int = 180) -> list[dict]:
    """Search upcoming events whose summary contains `name`."""
    from datetime import timedelta
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)
    params = urllib.parse.urlencode({
        "q":           name,
        "timeMin":     now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timeMax":     cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "singleEvents": "true",
        "orderBy":      "startTime",
    })
    result = _api("GET", f"/calendars/{CALENDAR_ID}/events?{params}")
    return result.get("items", [])


def _room_color(rooms: list[str]) -> str:
    """Google Calendar color IDs by room combo."""
    if set(rooms) >= {"gallery", "entrance", "kitchen", "cave"}:
        return "11"   # Tomato — full space
    if "kitchen" in rooms:
        return "6"    # Tangerine
    if "cave" in rooms:
        return "3"    # Grape
    if "entrance" in rooms and "gallery" in rooms:
        return "2"    # Sage
    if "gallery" in rooms:
        return "7"    # Peacock
    if "entrance" in rooms:
        return "5"    # Banana
    return "1"        # Lavender — default


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import timedelta
    test_start = datetime(2026, 5, 1, 18, 0)
    test_end   = datetime(2026, 5, 1, 22, 0)
    ev = create_booking(
        client_name  = "Test Booking",
        event_type   = "Test",
        rooms        = ["gallery", "entrance"],
        start_dt     = test_start,
        end_dt       = test_end,
        guest_count  = 10,
        email        = "test@example.com",
        notes        = "Created by booking bot test",
    )
    print("Created:", ev.get("htmlLink"))
    # Clean up
    cancel_booking(ev["id"])
    print("Cleaned up test event ✓")
