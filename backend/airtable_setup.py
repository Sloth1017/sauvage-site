"""
airtable_setup.py
-----------------
One-time script to create the Sauvage Airtable base with all required tables and fields.

Run once when setting up a new base:
    python airtable_setup.py

Requirements:
    pip install requests python-dotenv

Before running:
    1. Create a free Airtable account at airtable.com
    2. Create a new empty base called "Sauvage Bookings"
    3. Get your Personal Access Token:
       → airtable.com/create/tokens
       → Scopes needed: data.records:read, data.records:write,
                        schema.bases:read, schema.bases:write
       → Base access: grant access to your "Sauvage Bookings" base
    4. Copy your Base ID from the URL:
       → airtable.com/appXXXXXXXXXXXX/...  ← that's your Base ID
    5. Set environment variables in a .env file:
       AIRTABLE_API_KEY=patXXXXXXXXXXXXXXXXXX
       AIRTABLE_BASE_ID=appXXXXXXXXXXXXXXXX
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

try:
    from config import AIRTABLE_API_KEY as API_KEY, AIRTABLE_BASE_ID as BASE_ID
except ImportError:
    API_KEY = os.getenv("AIRTABLE_API_KEY")
    BASE_ID = os.getenv("AIRTABLE_BASE_ID")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json",
}

META_URL = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"


# ---------------------------------------------------------------------------
# Table schemas
# ---------------------------------------------------------------------------

INQUIRIES_FIELDS = [
    # --- Identity ---
    {"name": "Session ID",        "type": "singleLineText"},
    {"name": "Timestamp",         "type": "dateTime",
     "options": {"dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"},
                 "timeZone": "Europe/Amsterdam"}},

    # --- Funnel ---
    {"name": "Funnel Stage", "type": "singleSelect",
     "options": {"choices": [
         {"name": "1_event_type"},
         {"name": "2_date_time"},
         {"name": "3_contact"},
         {"name": "4_rooms"},
         {"name": "5_addons"},
         {"name": "6_quoted"},
         {"name": "7_deposit_pending"},
         {"name": "8_confirmed"},
         {"name": "abandoned"},
         {"name": "waitlisted"},
     ]}},

    {"name": "Booking Status", "type": "singleSelect",
     "options": {"choices": [
         {"name": "inquiry"},
         {"name": "deposit_pending"},
         {"name": "confirmed"},
         {"name": "cancelled"},
         {"name": "abandoned"},
     ]}},

    # --- Client ---
    {"name": "Client Name",    "type": "singleLineText"},
    {"name": "Customer Type",  "type": "singleSelect",
     "options": {"choices": [{"name": "Business"}, {"name": "Private"}]}},
    {"name": "Email",          "type": "email"},
    {"name": "Phone",          "type": "phoneNumber"},

    # --- Event ---
    {"name": "Event Type", "type": "singleSelect",
     "options": {"choices": [
         {"name": "Birthday"},
         {"name": "Corporate"},
         {"name": "Pop-up"},
         {"name": "Workshop"},
         {"name": "Themed Dinner"},
         {"name": "Music Event"},
         {"name": "Wine Tasting"},
         {"name": "Other"},
     ]}},
    {"name": "Requested Date", "type": "date",
     "options": {"dateFormat": {"name": "iso"}}},
    {"name": "Time Slot",      "type": "singleLineText"},
    {"name": "Duration",       "type": "singleSelect",
     "options": {"choices": [
         {"name": "Hourly"},
         {"name": "Half-Day"},
         {"name": "Full-Day"},
     ]}},
    {"name": "Hours",          "type": "number",
     "options": {"precision": 0}},
    {"name": "Booking Block",  "type": "singleSelect",
     "options": {"choices": [
         {"name": "Single Day"},
         {"name": "Weekend (3 days)"},
         {"name": "Week (7+ days)"},
         {"name": "Month (28+ days)"},
     ]}},
    {"name": "Guest Count",    "type": "number",
     "options": {"precision": 0}},
    {"name": "Arrival Time",   "type": "singleLineText"},

    # --- Rooms & Add-ons ---
    {"name": "Rooms Requested", "type": "multipleSelects",
     "options": {"choices": [
         {"name": "Upstairs (Gallery)"},
         {"name": "Entrance"},
         {"name": "Kitchen"},
         {"name": "Cave"},
     ]}},
    {"name": "Add-Ons", "type": "multipleSelects",
     "options": {"choices": [
         {"name": "Dishware & Cutlery"},
         {"name": "Stem Glassware"},
         {"name": "Staff Support"},
         {"name": "Extended Hours (after midnight)"},
         {"name": "Event Cleanup"},
         {"name": "Light Snacks Fento"},
         {"name": "Snacks Fento"},
         {"name": "Sommelier/Barista Service"},
         {"name": "Projector/Display Screen"},
     ]}},

    # --- Pricing ---
    {"name": "Bundle Discount %",        "type": "number",  "options": {"precision": 0}},
    {"name": "Closure Premiums Applied", "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
    {"name": "Total Incl VAT",           "type": "currency", "options": {"precision": 2, "symbol": "€"}},
    {"name": "Total Ex VAT",             "type": "currency", "options": {"precision": 2, "symbol": "€"}},
    {"name": "VAT Amount",               "type": "currency", "options": {"precision": 2, "symbol": "€"}},
    {"name": "Deposit Amount Due",       "type": "currency", "options": {"precision": 2, "symbol": "€"}},
    {"name": "Deposit Collected",        "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
    {"name": "Stripe Payment Reference", "type": "singleLineText"},

    # --- Special Flags ---
    {"name": "Special Flags", "type": "multipleSelects",
     "options": {"choices": [
         {"name": "Wall Use - Gallery Approval Required"},
         {"name": "Music Requested"},
         {"name": "Ikinari Coffee Overlap"},
         {"name": "Fento Snack Deadline"},
         {"name": "Kitchen Deposit Required"},
         {"name": "Early Access Requested"},
         {"name": "Escalation Required"},
     ]}},

    # --- Attribution ---
    {"name": "Referral Source", "type": "singleSelect",
     "options": {"choices": [
         {"name": "Greg"},
         {"name": "Dorian"},
         {"name": "Bart"},
         {"name": "Instagram"},
         {"name": "Google"},
         {"name": "Organic"},
         {"name": "Other"},
     ]}},
    {"name": "Attributed Host", "type": "singleSelect",
     "options": {"choices": [
         {"name": "Greg"},
         {"name": "Dorian"},
         {"name": "Bart"},
         {"name": "Unattributed"},
     ]}},
    {"name": "Referred By",    "type": "singleLineText"},
    {"name": "Referral Notes", "type": "singleLineText"},

    # --- Misc ---
    {"name": "Notes",            "type": "multilineText"},
    {"name": "Session Snapshot", "type": "multilineText"},
]


WAITLIST_FIELDS = [
    {"name": "Client Name",    "type": "singleLineText"},
    {"name": "Email",          "type": "email"},
    {"name": "Phone",          "type": "phoneNumber"},
    {"name": "Requested Date", "type": "date",
     "options": {"dateFormat": {"name": "iso"}}},
    {"name": "Event Type",     "type": "singleLineText"},
    {"name": "Rooms Interested", "type": "multipleSelects",
     "options": {"choices": [
         {"name": "Upstairs (Gallery)"},
         {"name": "Entrance"},
         {"name": "Kitchen"},
         {"name": "Cave"},
     ]}},
    {"name": "Guest Count", "type": "number", "options": {"precision": 0}},
    {"name": "Date Added",  "type": "dateTime",
     "options": {"dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"},
                 "timeZone": "Europe/Amsterdam"}},
    {"name": "Status", "type": "singleSelect",
     "options": {"choices": [
         {"name": "Waiting"},
         {"name": "Notified"},
         {"name": "Converted"},
         {"name": "Expired"},
     ]}},
    {"name": "Notes", "type": "multilineText"},
]


# ---------------------------------------------------------------------------
# Create tables
# ---------------------------------------------------------------------------

def create_table(name: str, fields: list, description: str = "") -> dict:
    """Create a table in the base via Airtable Metadata API."""
    payload = {
        "name":        name,
        "description": description,
        "fields":      fields,
    }
    resp = requests.post(META_URL, headers=HEADERS, json=payload)
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to create table '{name}': {resp.status_code}\n{resp.text}"
        )
    return resp.json()


def main():
    if not API_KEY or not BASE_ID:
        raise EnvironmentError(
            "AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set. "
            "Create a .env file or export them before running this script."
        )

    print(f"Setting up Sauvage Airtable base: {BASE_ID}\n")

    print("Creating 'Inquiries' table...")
    result = create_table(
        name="Inquiries",
        fields=INQUIRIES_FIELDS,
        description=(
            "Every booking inquiry, tracked in real time through the funnel. "
            "One record per conversation session."
        ),
    )
    print(f"  ✓ Inquiries table created (ID: {result.get('id')})")

    print("Creating 'Waitlist' table...")
    result = create_table(
        name="Waitlist",
        fields=WAITLIST_FIELDS,
        description="Clients waiting for availability on a specific date.",
    )
    print(f"  ✓ Waitlist table created (ID: {result.get('id')})\n")

    print("Setup complete.")
    print(
        "\nNext steps:\n"
        "  1. Open your Airtable base and verify both tables look correct.\n"
        "  2. In the Inquiries table, set up a grouped view by 'Funnel Stage'\n"
        "     to see your booking funnel at a glance.\n"
        "  3. Set up a view filtered to 'Booking Status = abandoned' for follow-up.\n"
        "  4. Optional: connect Airtable automations for Slack/email notifications\n"
        "     when a new record hits stage '8_confirmed'.\n"
    )


if __name__ == "__main__":
    main()
