"""
sauvage_airtable_client.py
--------------------------
Drop-in Airtable integration for the Sauvage Event Space booking chatbot.

Requires:
    pip install pyairtable python-dotenv

Environment variables (set in .env or your deployment config):
    AIRTABLE_API_KEY   — your personal access token from airtable.com/create/tokens
    AIRTABLE_BASE_ID   — found in the Airtable URL: airtable.com/appXXXXXXXX/...

Tables used:
    Inquiries   — every conversation, updated in real time as funnel stage advances
    Waitlist    — clients waiting for a specific date
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional
from pyairtable import Api

# ---------------------------------------------------------------------------
# Config — reads from config.py, falls back to environment variables
# ---------------------------------------------------------------------------

try:
    from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID
except ImportError:
    AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
    AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

INQUIRIES_TABLE  = "Inquiries"
WAITLIST_TABLE   = "Waitlist"

# Funnel stages — in order
FUNNEL_STAGES = [
    "1_event_type",
    "2_date_time",
    "3_contact",
    "4_rooms",
    "5_addons",
    "6_quoted",
    "7_deposit_pending",
    "8_confirmed",
    "abandoned",
    "waitlisted",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_table(table_name: str):
    api = Api(AIRTABLE_API_KEY)
    return api.table(AIRTABLE_BASE_ID, table_name)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_list(value) -> list:
    """Ensure a value is a list (for multi-select fields)."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ---------------------------------------------------------------------------
# INQUIRIES — core booking funnel
# ---------------------------------------------------------------------------

def create_inquiry(session_id: str, event_type: str) -> str:
    """
    Create a new inquiry record when a conversation starts.
    Returns the Airtable record ID — store this in your session state.

    Call this as soon as the client states their event type (stage 1).
    If the event_type value is not a valid Airtable select option, we fall back
    to creating the record without it and storing the value in Notes instead.
    """
    table = _get_table(INQUIRIES_TABLE)
    base_fields = {
        "Session ID":     session_id,
        "Funnel Stage":   "1_event_type",
        "Timestamp":      _now_iso(),
        "Booking Status": "inquiry",
    }
    try:
        record = table.create({**base_fields, "Event Type": event_type})
    except Exception as e:
        if "INVALID_MULTIPLE_CHOICE_OPTIONS" in str(e) or "INVALID_VALUE_FOR_COLUMN" in str(e):
            # event_type not in the Airtable select options — create without it
            # and store as a note so no data is lost
            base_fields["Notes"] = f"Event type (unrecognised option): {event_type}"
            record = table.create(base_fields)
        else:
            raise
    return record["id"]


def update_inquiry(record_id: str, fields: dict) -> dict:
    """
    Update any fields on an existing inquiry.
    Use this to progressively add data as the conversation moves forward.

    Multi-select fields (Rooms Requested, Add-Ons, Special Flags) are
    coerced to lists. If Airtable rejects a multi-select value (unrecognised option),
    we retry without that field and save the raw value in Notes instead — so the rest
    of the update always lands.

    Example:
        update_inquiry(record_id, {
            "Client Name": "Anna",
            "Email": "anna@example.com",
            "Phone": "+31612345678",
            "Funnel Stage": "3_contact",
        })
    """
    table = _get_table(INQUIRIES_TABLE)
    MULTI_FIELDS = ["Rooms Requested", "Add-Ons", "Special Flags"]

    # Fields that don't exist in the live base — strip before every call
    _BLOCKED_FIELDS = {"Deposit Amount Due"}
    fields = {k: v for k, v in fields.items() if k not in _BLOCKED_FIELDS}

    # Ensure multi-select fields are lists
    for mf in MULTI_FIELDS:
        if mf in fields:
            fields[mf] = _safe_list(fields[mf])

    def _safe_update(flds: dict, attempt: int = 0) -> dict:
        """Try the update; on known recoverable errors strip the bad field and retry once."""
        if not flds:
            return {}
        try:
            return table.update(record_id, flds)
        except Exception as e:
            if attempt >= 3:
                raise
            err = str(e)
            # Bad multi-select value — strip all multi-select fields, stash in Notes
            if "INVALID_MULTIPLE_CHOICE_OPTIONS" in err or "INVALID_VALUE_FOR_COLUMN" in err:
                notes_parts = []
                safe = {}
                for k, v in flds.items():
                    if k in MULTI_FIELDS:
                        notes_parts.append(f"{k}: {v}")
                    else:
                        safe[k] = v
                if notes_parts:
                    existing = safe.get("Notes", "")
                    safe["Notes"] = f"{existing} [{' | '.join(notes_parts)}]".strip(" |")
                print(f"[Airtable] Multi-select error — retrying without: {notes_parts}. Error: {e}")
                return _safe_update(safe, attempt + 1)
            # Unknown field name — extract the offending field name and drop it
            if "UNKNOWN_FIELD_NAME" in err:
                import re as _re
                bad = _re.search(r'Unknown field name: "([^"]+)"', err)
                if bad:
                    bad_field = bad.group(1)
                    safe = {k: v for k, v in flds.items() if k != bad_field}
                    print(f"[Airtable] Unknown field '{bad_field}' — retrying without it")
                    return _safe_update(safe, attempt + 1)
            raise

    try:
        return _safe_update(fields)
    except Exception as e:
        raise


def advance_stage(record_id: str, stage: str, extra_fields: dict = None) -> dict:
    """
    Move the funnel stage forward and optionally update other fields in one call.

    Args:
        record_id:    Airtable record ID
        stage:        One of FUNNEL_STAGES
        extra_fields: Any additional field updates to apply at the same time

    Example:
        advance_stage(record_id, "4_rooms", {
            "Rooms Requested": ["Upstairs", "Cave"],
            "Guest Count": 18,
        })
    """
    assert stage in FUNNEL_STAGES, f"Unknown stage: {stage}. Valid: {FUNNEL_STAGES}"
    fields = {"Funnel Stage": stage}
    if extra_fields:
        fields.update(extra_fields)
    return update_inquiry(record_id, fields)


def save_contact_details(record_id: str, name: str, email: str, phone: str,
                          customer_type: str) -> dict:
    """
    Save contact info — call this when stage moves to 3_contact.
    customer_type: "Business" or "Private"
    """
    return advance_stage(record_id, "3_contact", {
        "Client Name":    name,
        "Email":          email,
        "Phone":          phone,
        "Customer Type":  customer_type,
    })


def save_rooms_and_date(record_id: str, rooms: list, requested_date: str,
                         time_slot: str, duration: str,
                         hours: Optional[int] = None,
                         guest_count: Optional[int] = None,
                         booking_block: Optional[str] = None) -> dict:
    """
    Save date/time, guest count, booking block, and room selection —
    call when stage moves to 4_rooms.

    Args:
        rooms:          list, e.g. ["Upstairs (Gallery)", "Kitchen"]
        requested_date: ISO date string, e.g. "2026-04-15"
        time_slot:      e.g. "16:00-00:00"
        duration:       "Hourly", "Half-Day", or "Full-Day"
        hours:          number of hours if duration == "Hourly"
        guest_count:    number of guests (max 30)
        booking_block:  "Single Day", "Weekend (3 days)", "Week (7+ days)",
                        or "Month (28+ days)"
    """
    fields = {
        "Rooms Requested": rooms,
        "Requested Date":  requested_date,
        "Time Slot":       time_slot,
        "Duration":        duration,
    }
    if hours is not None:
        fields["Hours"] = hours
    if guest_count is not None:
        fields["Guest Count"] = guest_count
    if booking_block is not None:
        fields["Booking Block"] = booking_block
    return advance_stage(record_id, "4_rooms", fields)


def save_addons(record_id: str, addons: list, special_flags: list = None) -> dict:
    """
    Save selected add-ons and any special flags — call when stage moves to 5_addons.

    addons:        e.g. ["Stem Glassware", "Staff Support", "Projector/Display Screen"]
    special_flags: e.g. ["Wall Use - Gallery Approval Required", "Ikinari Overlap",
                          "Fento Snack Deadline", "Kitchen Deposit Required"]
    """
    fields = {"Add-Ons": addons}
    if special_flags:
        fields["Special Flags"] = special_flags
    return advance_stage(record_id, "5_addons", fields)


def save_quote(record_id: str, total_incl_vat: float, total_ex_vat: float,
               vat_amount: float, deposit_amount: float,
               bundle_discount_pct: int = 0,
               closure_premiums_applied: bool = False) -> dict:
    """
    Save the calculated quote — call when stage moves to 6_quoted.
    All amounts in EUR.
    """
    return advance_stage(record_id, "6_quoted", {
        "Total Incl VAT":           total_incl_vat,
        "Total Ex VAT":             total_ex_vat,
        "VAT Amount":               vat_amount,
        "Deposit Amount Due":       deposit_amount,
        "Bundle Discount %":        bundle_discount_pct,
        "Closure Premiums Applied": closure_premiums_applied,
    })


def mark_deposit_pending(record_id: str, stripe_payment_reference: str) -> dict:
    """Call when Stripe payment link is sent but payment not yet confirmed."""
    return advance_stage(record_id, "7_deposit_pending", {
        "Stripe Payment Reference": stripe_payment_reference,
        "Booking Status":           "deposit_pending",
    })


def confirm_booking(record_id: str, arrival_time: str = None) -> dict:
    """
    Mark booking as fully confirmed after Stripe payment received.
    arrival_time: optional, e.g. "14:30" (if client provided setup arrival time)
    """
    fields = {
        "Deposit Collected": True,
        "Booking Status":    "confirmed",
    }
    if arrival_time:
        fields["Arrival Time"] = arrival_time
    return advance_stage(record_id, "8_confirmed", fields)


def save_attribution(record_id: str, referral_source: str,
                      attributed_host: str = None,
                      referred_by: str = None,
                      referral_notes: str = None) -> dict:
    """
    Save attribution / referral data.

    referral_source:  "Instagram", "Google", "Organic", "Other", "Greg", "Dorian", "Bart"
    attributed_host:  "Greg", "Dorian", "Bart", or "Unattributed"
    referred_by:      verbatim name if someone specific was mentioned
    referral_notes:   any extra context
    """
    fields = {"Referral Source": referral_source}
    if attributed_host:
        fields["Attributed Host"] = attributed_host
    if referred_by:
        fields["Referred By"] = referred_by
    if referral_notes:
        fields["Referral Notes"] = referral_notes
    return update_inquiry(record_id, fields)


def mark_abandoned(record_id: str, notes: str = None) -> dict:
    """
    Mark inquiry as abandoned (no response for 24h+).
    Called by your automated drop-off monitoring job.
    """
    fields = {
        "Funnel Stage":   "abandoned",
        "Booking Status": "abandoned",
    }
    if notes:
        fields["Notes"] = notes
    return update_inquiry(record_id, fields)


def save_notes(record_id: str, notes: str) -> dict:
    """Append or overwrite the Notes field."""
    return update_inquiry(record_id, {"Notes": notes})


def get_inquiry(record_id: str) -> dict:
    """Retrieve full inquiry record by Airtable record ID."""
    table = _get_table(INQUIRIES_TABLE)
    return table.get(record_id)


def get_confirmed_inquiry_by_email(email: str) -> Optional[dict]:
    """
    Find the most recent confirmed booking for a given email address.
    Used to link a selectionsauvage.nl wine order back to a booking record.
    """
    table = _get_table(INQUIRIES_TABLE)
    formula = (
        f"AND("
        f"  {{Email}} = '{email}', "
        f"  {{Booking Status}} = 'confirmed'"
        f")"
    )
    records = table.all(formula=formula, sort=[("Timestamp", "desc")])
    return records[0] if records else None


def get_inquiry_by_session(session_id: str) -> Optional[dict]:
    """
    Look up an existing inquiry by your chatbot's session ID.
    Useful for resuming a dropped conversation.
    """
    table = _get_table(INQUIRIES_TABLE)
    records = table.all(formula=f"{{Session ID}} = '{session_id}'")
    if records:
        return records[0]
    return None


def get_bookings_for_date(date: str) -> list:
    """
    Return all confirmed or pending bookings for a given date.
    Use this to check availability before confirming.

    date: ISO date string, e.g. "2026-04-15"
    """
    table = _get_table(INQUIRIES_TABLE)
    formula = (
        f"AND("
        f"  {{Requested Date}} = '{date}', "
        f"  OR({{Booking Status}} = 'confirmed', {{Booking Status}} = 'deposit_pending')"
        f")"
    )
    return table.all(formula=formula)


def is_date_available(date: str) -> bool:
    """
    Returns True if the date has no confirmed or pending bookings.
    Note: does NOT check Google Calendar — do that separately.
    """
    existing = get_bookings_for_date(date)
    return len(existing) == 0


# ---------------------------------------------------------------------------
# WAITLIST
# ---------------------------------------------------------------------------

def add_to_waitlist(client_name: str, email: str, phone: str,
                     requested_date: str, event_type: str,
                     rooms_interested: list, guest_count: int,
                     notes: str = None) -> str:
    """
    Add a client to the waitlist for a specific date.
    Returns the Airtable record ID.
    """
    table = _get_table(WAITLIST_TABLE)
    fields = {
        "Client Name":       client_name,
        "Email":             email,
        "Phone":             phone,
        "Requested Date":    requested_date,
        "Event Type":        event_type,
        "Rooms Interested":  _safe_list(rooms_interested),
        "Guest Count":       guest_count,
        "Date Added":        _now_iso(),
        "Status":            "Waiting",
    }
    if notes:
        fields["Notes"] = notes
    record = table.create(fields)
    return record["id"]


def get_waitlist_for_date(date: str) -> list:
    """Return all Waiting clients for a given date, in order added."""
    table = _get_table(WAITLIST_TABLE)
    formula = f"AND({{Requested Date}} = '{date}', {{Status}} = 'Waiting')"
    records = table.all(formula=formula, sort=["Date Added"])
    return records


def update_waitlist_status(record_id: str,
                            status: str,
                            notes: str = None) -> dict:
    """
    Update waitlist entry status.
    status: "Waiting", "Notified", "Converted", "Expired"
    """
    valid = {"Waiting", "Notified", "Converted", "Expired"}
    assert status in valid, f"Invalid status. Must be one of: {valid}"
    fields = {"Status": status}
    if notes:
        fields["Notes"] = notes
    table = _get_table(WAITLIST_TABLE)
    return table.update(record_id, fields)


def notify_next_on_waitlist(date: str) -> Optional[dict]:
    """
    When a cancellation occurs: find the next Waiting client for that date,
    mark them as Notified, and return their record so you can send a message.
    Returns None if waitlist is empty.
    """
    waitlist = get_waitlist_for_date(date)
    if not waitlist:
        return None
    next_client = waitlist[0]
    update_waitlist_status(next_client["id"], "Notified")
    return next_client


# ---------------------------------------------------------------------------
# Convenience: session state snapshot
# ---------------------------------------------------------------------------

def snapshot_session(record_id: str, session_data: dict) -> dict:
    """
    Serialise your entire session state dict to the Notes field as JSON.
    Useful for mid-session drop-off recovery — store whatever you need.
    """
    snapshot = json.dumps(session_data, ensure_ascii=False, default=str)
    return update_inquiry(record_id, {"Session Snapshot": snapshot})


def submit_feedback(booking_record_id: str, client_name: str, event_type: str,
                     rating: int, highlight: str, improve: str, comment: str) -> str:
    """
    Write a feedback submission to the Feedback table.
    booking_record_id: Airtable record ID from the Inquiries table (links the two rows).
    Returns the new Feedback record ID.
    """
    table = _get_table("Feedback")
    date_str = _now_iso()[:10]
    fields = {
        "Name":         f"{client_name} — {date_str}",
        "Submitted At": _now_iso(),
    }
    if booking_record_id:
        fields["Bookings"] = [booking_record_id]
    if rating:
        try:
            fields["Rating"] = int(rating)
        except (ValueError, TypeError):
            pass
    if highlight:
        fields["Highlight"] = highlight
    if improve:
        fields["Improvement"] = improve
    if comment:
        fields["Comment"] = comment
    record = table.create(fields)
    return record["id"]


def restore_session_snapshot(record_id: str) -> Optional[dict]:
    """
    Retrieve and deserialise the session snapshot from a previous conversation.
    Returns None if no snapshot exists.
    """
    record = get_inquiry(record_id)
    raw = record.get("fields", {}).get("Session Snapshot")
    if raw:
        return json.loads(raw)
    return None
