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
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Union

# ── Config ────────────────────────────────────────────────────────────────────
CALENDAR_ID      = "sauvagespace.reservations@gmail.com"
AIRTABLE_BASE_ID = "app4rCwUqnJ5A28YH"
AIRTABLE_TABLE_ID = "tbledNkWpyzbT8J27"  # Inquiries

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


# ── Room normalisation ────────────────────────────────────────────────────────

_ROOM_ALIASES: dict[str, str] = {
    # canonical keys used internally
    "gallery":           "gallery",
    "entrance":          "entrance",
    "kitchen":           "kitchen",
    "cave":              "cave",
    # display names from session state / Airtable
    "upstairs (gallery)": "gallery",
    "gallery (upstairs)": "gallery",
    "upstairs":           "gallery",
    "upstairs gallery":   "gallery",
    "gallery upstairs":   "gallery",
}

def _norm_room(r: str) -> str:
    """Map any room string variant to a canonical key, or return '' if unknown."""
    return _ROOM_ALIASES.get(r.strip().lower(), "")


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
    keys = [_norm_room(r) for r in rooms]
    keys = [k for k in keys if k]  # drop unrecognised

    room_parts = [room_labels[k] for k in keys if k in room_labels]

    if set(keys) >= {"gallery", "entrance", "kitchen", "cave"}:
        prefix = "FULL SPACE"
    elif len(room_parts) > 1:
        prefix = "+".join(room_parts)
    else:
        prefix = room_parts[0] if room_parts else "EVENT"

    return f"{prefix}- {client_name} ({event_type})"


# ── Public API ────────────────────────────────────────────────────────────────

def create_booking(
    client_name:   str,
    event_type:    str,
    rooms:         list[str],
    start_dt:      datetime,
    end_dt:        datetime,
    guest_count:   int = 0,
    email:         str = "",
    phone:         str = "",
    notes:         str = "",
    airtable_id:   str = "",
    arrival_time:  str = "",   # e.g. "14:30" — setup/arrival before event
) -> dict:
    """
    Create a Google Calendar event for a confirmed booking.
    Returns the created event dict (includes 'id' and 'htmlLink').
    """
    title = _build_title(rooms, client_name, event_type)

    # Human-readable room names (preserve original strings)
    rooms_display = ", ".join(r for r in rooms) if rooms else "—"

    description = (
        f"Client: {client_name}\n"
        f"Email: {email}\n"
        f"Phone: {phone}\n"
        f"Event: {event_type}\n"
        f"Rooms: {rooms_display}\n"
        f"Guests: {guest_count}\n"
    )
    if arrival_time:
        description += f"Arrival / setup time: {arrival_time}\n"
    if notes:
        description += f"Notes: {notes}\n"
    if airtable_id:
        at_url = (
            f"https://airtable.com/{AIRTABLE_BASE_ID}"
            f"/{AIRTABLE_TABLE_ID}/{airtable_id}"
        )
        description += f"\nAirtable: {at_url}\n"
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


def create_booking_series(
    dates:         Union[list[str], str],
    start_time_str: str,
    end_time_str:   str,
    client_name:   str,
    event_type:    str,
    rooms:         list[str],
    guest_count:   int = 0,
    email:         str = "",
    phone:         str = "",
    notes:         str = "",
    airtable_id:   str = "",
    arrival_time:  str = "",
) -> list[dict]:
    """
    Create one calendar event per day for a multi-day booking.

    `dates` can be:
      - a list of ISO date strings  ["2026-05-15", "2026-05-16", ...]
      - a two-item list [start, end] which is expanded into every date in range
      - a single date string (falls back to create_booking)

    Returns a list of created event dicts (each has 'id' and 'htmlLink').
    """
    # Normalise to a list of date strings
    if isinstance(dates, str):
        date_list = [dates.strip()]
    else:
        date_list = [d.strip() for d in dates if d]

    # If exactly two dates that differ, treat as [start, end] range and expand
    if len(date_list) == 2 and date_list[0] != date_list[1]:
        try:
            d_start = datetime.strptime(date_list[0], "%Y-%m-%d").date()
            d_end   = datetime.strptime(date_list[1], "%Y-%m-%d").date()
            if d_end > d_start:
                date_list = [
                    (d_start + timedelta(days=i)).isoformat()
                    for i in range((d_end - d_start).days + 1)
                ]
        except ValueError:
            pass  # leave as-is if parse fails

    events = []
    for ds in date_list:
        try:
            start_dt = datetime.strptime(f"{ds} {start_time_str}", "%Y-%m-%d %H:%M")
            end_dt   = datetime.strptime(f"{ds} {end_time_str}",   "%Y-%m-%d %H:%M")
        except ValueError as e:
            print(f"[Calendar] Skipping date {ds}: {e}")
            continue

        ev = create_booking(
            client_name  = client_name,
            event_type   = event_type,
            rooms        = rooms,
            start_dt     = start_dt,
            end_dt       = end_dt,
            guest_count  = guest_count,
            email        = email,
            phone        = phone,
            notes        = notes,
            airtable_id  = airtable_id,
            arrival_time = arrival_time,
        )
        events.append(ev)

    return events


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
    """Google Calendar color IDs by room combo (accepts any room name variant)."""
    keys = {_norm_room(r) for r in rooms}
    if keys >= {"gallery", "entrance", "kitchen", "cave"}:
        return "11"   # Tomato — full space
    if "kitchen" in keys:
        return "6"    # Tangerine
    if "cave" in keys:
        return "3"    # Grape
    if "entrance" in keys and "gallery" in keys:
        return "2"    # Sage
    if "gallery" in keys:
        return "7"    # Peacock
    if "entrance" in keys:
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
