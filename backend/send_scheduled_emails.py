#!/usr/bin/env python3
"""
send_scheduled_emails.py
------------------------
Daily cron script — run once per day (recommended: 08:00 Amsterdam time).

For every confirmed Sauvage booking it checks:
  • tomorrow's date  → send day_before email
  • today's date     → send day_of email
  • yesterday's date → send day_after (feedback) email

A local SQLite log prevents duplicate sends even if the script is run
multiple times in one day.

Usage:
    python send_scheduled_emails.py [--dry-run] [--date YYYY-MM-DD]

    --dry-run        Print what would be sent without actually sending.
    --date           Override "today" — useful for backfill / testing.
                     e.g.  --date 2026-05-20
"""

import argparse
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
# Prefer running from /var/www/sauvage on the server
for _base in [_HERE, Path("/var/www/sauvage")]:
    if (_base / "airtable_client.py").exists():
        sys.path.insert(0, str(_base))
        break

from airtable_client import _get_table, INQUIRIES_TABLE
from event_emails    import send_day_before, send_day_of, send_day_after

# ── Email log DB ──────────────────────────────────────────────────────────────
_LOG_DB = _HERE / "email_log.db"

def _init_log():
    conn = sqlite3.connect(_LOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_log (
            record_id  TEXT NOT NULL,
            email_type TEXT NOT NULL,   -- day_before | day_of | day_after
            sent_at    TEXT NOT NULL,
            PRIMARY KEY (record_id, email_type)
        )
    """)
    conn.commit()
    return conn


def _already_sent(conn, record_id: str, email_type: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM email_log WHERE record_id = ? AND email_type = ?",
        (record_id, email_type),
    ).fetchone()
    return bool(row)


def _mark_sent(conn, record_id: str, email_type: str):
    conn.execute(
        "INSERT OR IGNORE INTO email_log (record_id, email_type, sent_at) VALUES (?, ?, ?)",
        (record_id, email_type, datetime.utcnow().isoformat()),
    )
    conn.commit()


# ── Airtable helpers ──────────────────────────────────────────────────────────

def _get_confirmed_bookings(date_str: str) -> list:
    """Return all confirmed bookings for a given ISO date string."""
    table   = _get_table(INQUIRIES_TABLE)
    formula = (
        f"AND("
        f"  {{Requested Date}} = '{date_str}', "
        f"  {{Booking Status}} = 'confirmed'"
        f")"
    )
    return table.all(formula=formula)


def _record_to_state(record: dict) -> dict:
    """Map Airtable record fields to the state dict expected by event_emails."""
    f = record.get("fields", {})

    # Dates: Airtable returns "2026-04-20" for date fields
    raw_date = f.get("Requested Date", "")
    dates    = [raw_date] if raw_date else []

    # Rooms: multi-select → list
    rooms = f.get("Rooms Requested", [])
    if isinstance(rooms, str):
        rooms = [rooms]

    return {
        "client_name":     f.get("Client Name", ""),
        "email":           f.get("Email", ""),
        "phone":           f.get("Phone", ""),
        "event_type":      f.get("Event Type", "event"),
        "dates":           dates,
        "start_time":      (f.get("Time Slot") or "").split("-")[0].strip(),
        "end_time":        (f.get("Time Slot") or "").split("-")[-1].strip(),
        "rooms":           rooms,
        "guest_count":     f.get("Guest Count", ""),
        "attributed_host": f.get("Attributed Host", ""),
        "arrival_time":    f.get("Arrival Time", ""),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run(today: date, dry_run: bool = False):
    tomorrow  = today + timedelta(days=1)
    yesterday = today - timedelta(days=1)

    schedule = [
        (yesterday.isoformat(), "day_after",  send_day_after),
        (today.isoformat(),     "day_of",     send_day_of),
        (tomorrow.isoformat(),  "day_before", send_day_before),
    ]

    conn = _init_log()
    total_sent = total_skipped = total_errors = 0

    for date_str, email_type, send_fn in schedule:
        bookings = _get_confirmed_bookings(date_str)
        print(f"[{email_type}] {date_str} — {len(bookings)} confirmed booking(s)")

        for record in bookings:
            rid   = record["id"]
            state = _record_to_state(record)
            name  = state.get("client_name") or rid
            email = state.get("email", "(no email)")

            if _already_sent(conn, rid, email_type):
                print(f"  SKIP  {name} <{email}> — already sent")
                total_skipped += 1
                continue

            if dry_run:
                print(f"  DRY   {name} <{email}> — would send {email_type}")
                total_skipped += 1
                continue

            ok = send_fn(state)
            if ok:
                _mark_sent(conn, rid, email_type)
                print(f"  SENT  {name} <{email}>")
                total_sent += 1
            else:
                print(f"  ERROR {name} <{email}> — send failed")
                total_errors += 1

    conn.close()
    print(f"\nDone — sent: {total_sent}, skipped: {total_skipped}, errors: {total_errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Sauvage lifecycle emails.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without sending.")
    parser.add_argument("--date",    default="",          help="Override today (YYYY-MM-DD).")
    args = parser.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    print(f"Running for date: {today}  (dry_run={args.dry_run})")
    run(today, dry_run=args.dry_run)
