"""
add_community_fields.py
-----------------------
Adds two new fields to the Airtable Inquiries table for Community Pricing Mode:
  - community_pricing  (checkbox)
  - agreed_price       (currency, EUR)

Run once from your Mac:
    python3 add_community_fields.py
"""

import requests
import sys

try:
    from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID
except ImportError:
    print("ERROR: config.py not found.")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json",
}

# ── Step 1: Find the Inquiries table ID ───────────────────────────────────────

resp = requests.get(
    f"https://api.airtable.com/v0/meta/bases/{AIRTABLE_BASE_ID}/tables",
    headers=HEADERS,
)
resp.raise_for_status()

tables = resp.json().get("tables", [])
inquiries_table = next((t for t in tables if t["name"] == "Inquiries"), None)

if not inquiries_table:
    print("ERROR: 'Inquiries' table not found in this base.")
    sys.exit(1)

table_id = inquiries_table["id"]
print(f"✓ Found Inquiries table: {table_id}")

# ── Step 2: Check which fields already exist ──────────────────────────────────

existing_fields = {f["name"] for f in inquiries_table.get("fields", [])}
print(f"  Existing fields: {len(existing_fields)}")

# ── Step 3: Add new fields ────────────────────────────────────────────────────

new_fields = [
    {
        "name": "community_pricing",
        "type": "checkbox",
        "options": {"icon": "check", "color": "greenBright"},
    },
    {
        "name": "agreed_price",
        "type": "currency",
        "options": {"precision": 2, "symbol": "€"},
    },
]

for field in new_fields:
    if field["name"] in existing_fields:
        print(f"  ⚠ Field '{field['name']}' already exists — skipping.")
        continue

    r = requests.post(
        f"https://api.airtable.com/v0/meta/bases/{AIRTABLE_BASE_ID}/tables/{table_id}/fields",
        headers=HEADERS,
        json=field,
    )

    if r.status_code in (200, 201):
        print(f"  ✓ Added field: {field['name']}")
    else:
        print(f"  ✗ Failed to add '{field['name']}': {r.status_code} {r.text}")

print("\nDone.")
