"""
host_reminder.py
----------------
Daily cron script — sends Telegram reminders when no host has been
assigned to an upcoming confirmed booking.

Reminder windows:  7 days, 3 days, 1 day before the event.

Run daily at 09:00 Amsterdam time via cron:
  0 9 * * * /var/www/sauvage/venv/bin/python /root/sauvage/backend/host_reminder.py
"""

import os
import sys
from datetime import date, timedelta

# ── Load .env from same directory ─────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

REMINDER_DAYS = [7, 3, 1]


def get_upcoming_unhosted() -> list:
    """Return confirmed bookings that fall exactly 1, 3, or 7 days from today
    and have no host assigned."""
    try:
        from airtable_client import _get_table, INQUIRIES_TABLE
        table = _get_table(INQUIRIES_TABLE)

        target_dates = [
            (date.today() + timedelta(days=d)).isoformat()
            for d in REMINDER_DAYS
        ]

        # Build formula: confirmed + date in one of the target dates + no Host
        date_conditions = ", ".join(
            f"{{Requested Date}} = '{d}'" for d in target_dates
        )
        formula = (
            f"AND("
            f"  {{Booking Status}} = 'confirmed', "
            f"  OR({date_conditions}), "
            f"  OR({{Host}} = '', {{Host}} = BLANK())"
            f")"
        )
        records = table.all(formula=formula)
        return records
    except Exception as e:
        print(f"[HostReminder] Airtable query failed: {e}")
        return []


def days_until(event_date_str: str) -> int:
    try:
        event_date = date.fromisoformat(str(event_date_str)[:10])
        return (event_date - date.today()).days
    except Exception:
        return -1


def send_reminders():
    from telegram_notify import _post, _host_keyboard, TELEGRAM_CHAT_ID, _html_escape

    if not TELEGRAM_CHAT_ID:
        print("[HostReminder] TELEGRAM_CHAT_ID not set — skipping")
        return

    records = get_upcoming_unhosted()
    if not records:
        print("[HostReminder] No unhosted bookings in reminder window")
        return

    for rec in records:
        fields      = rec.get("fields", {})
        record_id   = rec.get("id", "")
        client_name = fields.get("Name", "Unknown")
        event_type  = fields.get("Event Type", "Event")
        event_date  = fields.get("Requested Date", "")
        time_slot   = fields.get("Time Slot", "")
        parts       = time_slot.split("-", 1) if "-" in time_slot else ["", ""]
        start_time  = parts[0].strip()
        end_time    = parts[1].strip() if len(parts) > 1 else ""
        rooms_raw   = fields.get("Rooms", [])
        rooms       = rooms_raw if isinstance(rooms_raw, list) else [rooms_raw]
        days_left   = days_until(event_date)

        if days_left not in REMINDER_DAYS:
            continue  # shouldn't happen but be safe

        urgency = "🔴" if days_left == 1 else ("🟡" if days_left == 3 else "🟠")
        day_label = f"{days_left} day{'s' if days_left != 1 else ''}"

        rooms_str = ", ".join(str(r) for r in rooms) if rooms else "—"

        text = (
            f"{urgency} <b>No host assigned — {day_label} to go</b>\n"
            f"\n"
            f"<b>Client:</b> {_html_escape(client_name)}\n"
            f"<b>Event:</b> {_html_escape(event_type)}\n"
            f"<b>Date:</b> {event_date}\n"
            f"<b>Time:</b> {start_time} – {end_time}\n"
            f"<b>Space:</b> {_html_escape(rooms_str)}\n"
            f"\n"
            f"👤 <b>Who's hosting?</b>"
        )

        keyboard = _host_keyboard(record_id)

        result = _post(
            "sendMessage",
            chat_id    = TELEGRAM_CHAT_ID,
            text       = text,
            parse_mode = "HTML",
            disable_web_page_preview = True,
            reply_markup = keyboard,
        )

        status = "✓" if result.get("ok") else f"✗ {result}"
        print(f"[HostReminder] {client_name} / {event_date} ({day_label}) → {status}")


if __name__ == "__main__":
    send_reminders()
