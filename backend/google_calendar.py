"""
google_calendar.py
------------------
Reads the Sauvage Space public Google Calendar ICS feed.

Key rules:
  - Each booking can cover MULTIPLE rooms (e.g. Gallery + Entrance + Kitchen)
  - Multiple clients CAN book on the same day/date as long as:
      a) They want DIFFERENT rooms, AND
      b) Their time slots don't OVERLAP on any shared room

Availability is therefore: per-room, per-time-slot — not per-date.
"""

import re
import urllib.request
from datetime import datetime, date, timedelta, timezone
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "sauvagespace.reservations%40gmail.com/public/basic.ics"
)

ROOMS = ["entrance", "gallery", "kitchen", "cave"]

CACHE_TTL_SECONDS = 900
_cache: dict = {"data": None, "fetched_at": None}


# ── Room detection from event title ──────────────────────────────────────────

def _detect_rooms(summary: str) -> list[str]:
    """
    Infer which rooms are booked from the calendar event SUMMARY.
    One booking can claim multiple rooms.
    """
    s = summary.upper()
    rooms = []

    # Full space shorthand
    if any(x in s for x in ["FULL SPACE", "FULL RENTAL", "HALF DAY FULL", "FULL DAY"]):
        return ROOMS[:]

    # Combined shorthands first
    if "GALLERY+ENTRANCE" in s or "ENTRANCE+GALLERY" in s:
        rooms += ["gallery", "entrance"]

    # Individual rooms
    if any(x in s for x in ["ENTRANCE", "ENTRY", "FRONT BAR"]) and "entrance" not in rooms:
        rooms.append("entrance")
    if any(x in s for x in ["GALLERY", "UPSTAIRS"]) and "gallery" not in rooms:
        rooms.append("gallery")
    if "WINE TASTING" in s and "gallery" not in rooms:
        rooms.append("gallery")
    if "KITCHEN" in s:
        rooms.append("kitchen")
    if "CAVE" in s:
        rooms.append("cave")

    # Default: gallery is the primary event space
    if not rooms:
        rooms.append("gallery")

    return rooms


# ── ICS Fetch & Parse ─────────────────────────────────────────────────────────

def _fetch_ics() -> str:
    now = datetime.now(timezone.utc)
    if (
        _cache["data"]
        and _cache["fetched_at"]
        and (now - _cache["fetched_at"]).total_seconds() < CACHE_TTL_SECONDS
    ):
        return _cache["data"]
    req = urllib.request.Request(ICS_URL, headers={"User-Agent": "SauvageBot/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    _cache["data"] = text
    _cache["fetched_at"] = now
    return text


def _get(block: str, key: str) -> str:
    m = re.search(
        rf"^{key}[^:\n]*:(.+?)(?=\r?\n[A-Z]|\r?\nEND:VEVENT)",
        block, re.MULTILINE | re.DOTALL,
    )
    if not m:
        return ""
    return re.sub(r"\r?\n[ \t]", "", m.group(1)).strip()


def _parse_dt(val: str) -> Optional[datetime]:
    val = val.strip().split(";")[-1]
    val = val.replace("Z", "")
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"):
        try:
            return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def get_booked_events(days_ahead: int = 180) -> list[dict]:
    """
    Return all upcoming events with rooms and time slots.

    Each item: {
        "summary":  str,
        "start":    datetime,
        "end":      datetime,
        "rooms":    [str, ...],   # rooms claimed by this booking
        "dates":    [date, ...],  # calendar dates spanned
    }
    """
    try:
        text = _fetch_ics()
    except Exception as e:
        print(f"[CalendarError] {e}")
        return []

    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)
    events = []

    for block in text.split("BEGIN:VEVENT")[1:]:
        summary = _get(block, "SUMMARY")
        start   = _parse_dt(_get(block, "DTSTART"))
        end     = _parse_dt(_get(block, "DTEND"))
        if not start or not end or start > cutoff or end < now:
            continue
        status = _get(block, "STATUS").upper()
        if status == "CANCELLED":
            continue

        dates = []
        d = start.date()
        while d <= end.date():
            dates.append(d)
            d += timedelta(days=1)

        events.append({
            "summary": summary,
            "start":   start,
            "end":     end,
            "rooms":   _detect_rooms(summary),
            "dates":   dates,
        })

    return events


# ── Core availability logic ───────────────────────────────────────────────────

def _times_overlap(start1: datetime, end1: datetime,
                   start2: datetime, end2: datetime) -> bool:
    """True if two time ranges overlap (exclusive end)."""
    return start1 < end2 and start2 < end1


def get_conflicts(
    requested_rooms: list[str],
    start_dt: datetime,
    end_dt: datetime,
) -> list[dict]:
    """
    Find existing bookings that conflict with the requested rooms + time slot.

    A conflict = same room AND overlapping time.
    Returns list of conflicting events.
    """
    conflicts = []
    for ev in get_booked_events():
        shared_rooms = set(ev["rooms"]) & set(requested_rooms)
        if not shared_rooms:
            continue  # different rooms — no conflict
        if _times_overlap(start_dt, end_dt, ev["start"], ev["end"]):
            conflicts.append({**ev, "shared_rooms": list(shared_rooms)})
    return conflicts


def is_available(
    requested_rooms: list[str],
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[bool, list[dict]]:
    """
    Check if ALL requested rooms are free for the given time slot.
    Returns (available: bool, conflicts: list)
    """
    conflicts = get_conflicts(requested_rooms, start_dt, end_dt)
    return len(conflicts) == 0, conflicts


# ── Human-readable helpers ────────────────────────────────────────────────────

def availability_summary(
    date_strings: list[str],
    requested_rooms: Optional[list[str]] = None,
    start_time: Optional[str] = None,   # "HH:MM"
    end_time:   Optional[str] = None,   # "HH:MM"
) -> str:
    """
    Human-readable availability summary for the chatbot.
    Checks per-room, per-time-slot — not just per-date.

    If no times given, checks the whole day (00:00–23:59) as a worst-case.
    If no rooms given, checks all rooms.
    """
    if requested_rooms is None:
        requested_rooms = ROOMS

    lines = []

    for ds in date_strings:
        try:
            d = date.fromisoformat(ds)
        except ValueError:
            lines.append(f"⚠️ {ds} — could not parse date")
            continue

        label = d.strftime("%A, %-d %B %Y")

        # Build datetimes for the requested slot
        if start_time and end_time:
            try:
                sh, sm = map(int, start_time.split(":"))
                eh, em = map(int, end_time.split(":"))
                slot_start = datetime(d.year, d.month, d.day, sh, sm, tzinfo=timezone.utc)
                slot_end   = datetime(d.year, d.month, d.day, eh, em, tzinfo=timezone.utc)
                time_label = f" · {start_time}–{end_time}"
            except Exception:
                slot_start = datetime(d.year, d.month, d.day, 0,  0,  tzinfo=timezone.utc)
                slot_end   = datetime(d.year, d.month, d.day, 23, 59, tzinfo=timezone.utc)
                time_label = ""
        else:
            slot_start = datetime(d.year, d.month, d.day, 0,  0,  tzinfo=timezone.utc)
            slot_end   = datetime(d.year, d.month, d.day, 23, 59, tzinfo=timezone.utc)
            time_label = ""

        conflicts = get_conflicts(requested_rooms, slot_start, slot_end)

        if not conflicts:
            rooms_label = ", ".join(r.capitalize() for r in requested_rooms)
            lines.append(f"✅ {label}{time_label} — {rooms_label} available")
        else:
            # Show which rooms are blocked and by whom
            blocked_rooms: dict[str, str] = {}
            for ev in conflicts:
                for room in ev["shared_rooms"]:
                    t = f"{ev['start'].strftime('%H:%M')}–{ev['end'].strftime('%H:%M')}"
                    blocked_rooms[room] = f"{ev['summary']} ({t})"

            free_rooms = [r for r in requested_rooms if r not in blocked_rooms]

            for room, reason in blocked_rooms.items():
                lines.append(f"❌ {label}{time_label} · {room.capitalize()} — taken by {reason}")
            if free_rooms:
                lines.append(f"   ✅ Still free that slot: {', '.join(r.capitalize() for r in free_rooms)}")

            # Suggest alternative slots
            alts = get_next_available_slots(requested_rooms, from_date=d, count=3)
            if alts:
                alt_strs = []
                for a in alts:
                    alt_strs.append(a["date"].strftime("%-d %b") +
                                    (f" {a['start']}–{a['end']}" if a.get("start") else ""))
                lines.append(f"   → Nearest free slots: {', '.join(alt_strs)}")

    return "\n".join(lines)


def get_next_available_slots(
    requested_rooms: list[str],
    from_date: Optional[date] = None,
    count: int = 3,
    preferred_start: str = "16:00",
    preferred_end:   str = "22:00",
) -> list[dict]:
    """
    Return next `count` date+time slots where ALL requested rooms are free.
    Defaults to checking evening slots (16:00–22:00).
    """
    if from_date is None:
        from_date = date.today()

    sh, sm = map(int, preferred_start.split(":"))
    eh, em = map(int, preferred_end.split(":"))

    available = []
    d = from_date + timedelta(days=1)  # start from tomorrow

    while len(available) < count:
        start_dt = datetime(d.year, d.month, d.day, sh, sm, tzinfo=timezone.utc)
        end_dt   = datetime(d.year, d.month, d.day, eh, em, tzinfo=timezone.utc)
        ok, _    = is_available(requested_rooms, start_dt, end_dt)
        if ok:
            available.append({"date": d, "start": preferred_start, "end": preferred_end})
        d += timedelta(days=1)
        if (d - from_date).days > 365:
            break

    return available


def calendar_snapshot(days: int = 60) -> str:
    """
    Per-room, per-day snapshot for injection into the chatbot system prompt.
    Shows concurrent bookings clearly — multiple clients on same day visible.
    """
    events = get_booked_events(days)
    if not events:
        return "No bookings in the next 60 days — all rooms available."

    # Group by date
    by_date: dict[date, list[dict]] = {}
    for ev in events:
        for d in ev["dates"]:
            by_date.setdefault(d, []).append(ev)

    lines = []
    for d in sorted(by_date.keys()):
        evs = by_date[d]

        # Per-room status for this date
        room_lines = []
        for room in ROOMS:
            room_evs = [ev for ev in evs if room in ev["rooms"]]
            if room_evs:
                slots = " | ".join(
                    f"{ev['summary']} {ev['start'].strftime('%H:%M')}–{ev['end'].strftime('%H:%M')}"
                    for ev in room_evs
                )
                room_lines.append(f"  {room.upper()}: BOOKED — {slots}")
            else:
                room_lines.append(f"  {room.upper()}: free")

        lines.append(d.strftime("%-d %b %Y") + ":")
        lines.extend(room_lines)

    return "\n".join(lines[:80])  # cap tokens


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Per-room calendar snapshot ===")
    print(calendar_snapshot(30))

    print("\n=== Check: Gallery + Entrance on 2026-04-05, 18:00–22:00 ===")
    print(availability_summary(["2026-04-05"], ["gallery", "entrance"], "18:00", "22:00"))

    print("\n=== Next 3 available slots for Kitchen ===")
    for s in get_next_available_slots(["kitchen"], count=3):
        print(f"  {s['date']} {s['start']}–{s['end']}")
