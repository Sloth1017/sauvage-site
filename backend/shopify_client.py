"""
shopify_client.py
-----------------
Shopify Draft Orders integration for Sauvage booking deposits.

Creates a Shopify checkout link for the deposit amount, sends it to the
client in chat, and stores the draft order ID in Airtable so the webhook
can confirm payment automatically.

All amounts in EUR. Shopify accepts prices as decimal strings (e.g. "50.00").

Requires:
    pip install requests

Shopify credentials (add to config.py):
    SHOPIFY_STORE_URL        — e.g. "sauvage.myshopify.com" (no https://)
    SHOPIFY_ADMIN_API_TOKEN  — Admin API access token from your Shopify app
    SHOPIFY_API_VERSION      — e.g. "2024-01" (update periodically)

How to get your Admin API token:
    1. Go to your Shopify Admin → Settings → Apps and sales channels
    2. Click "Develop apps" → Create an app (e.g. "Sauvage Chatbot")
    3. Under "Configuration" → Admin API scopes, enable:
         - write_draft_orders
         - read_draft_orders
         - read_orders
    4. Install the app → copy the Admin API access token

Deposit rules:
    Standard deposit:  €50.00
    Kitchen deposit:   €300.00 (€50 standard + €250 kitchen)
"""

import requests
import os

try:
    from config import SHOPIFY_STORE_URL, SHOPIFY_ADMIN_API_TOKEN, SHOPIFY_API_VERSION
except ImportError:
    SHOPIFY_STORE_URL       = os.getenv("SHOPIFY_STORE_URL")
    SHOPIFY_ADMIN_API_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN")
    SHOPIFY_API_VERSION     = os.getenv("SHOPIFY_API_VERSION", "2024-01")


def _headers() -> dict:
    return {
        "X-Shopify-Access-Token": SHOPIFY_ADMIN_API_TOKEN,
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    return f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}"


# ---------------------------------------------------------------------------
# Deposit amounts (EUR)
# ---------------------------------------------------------------------------

DEPOSIT_STANDARD = "50.00"
DEPOSIT_KITCHEN  = "300.00"   # €50 standard + €250 kitchen


def get_deposit_amount(kitchen_booked: bool) -> str:
    """Return deposit amount as a string for the Shopify API."""
    return DEPOSIT_KITCHEN if kitchen_booked else DEPOSIT_STANDARD


# ---------------------------------------------------------------------------
# Core: create a draft order and return the checkout URL
# ---------------------------------------------------------------------------

def create_checkout_session(
    airtable_record_id: str,
    client_email: str,
    client_name: str,
    event_type: str,
    event_date: str,
    kitchen_booked: bool = False,
    session_id: str = "",
) -> dict:
    """
    Create a Shopify Draft Order for the booking deposit.

    The draft order's invoice URL is the payment link you send to the client.
    When paid, Shopify fires an orders/paid webhook which confirms the booking
    in Airtable automatically (handled in shopify_webhook.py).

    Args:
        airtable_record_id: Stored in the draft order note and tags so the
                            webhook can find the right Airtable record.
        client_email:       Pre-fills the email in Shopify checkout.
        client_name:        Split into first/last for the Shopify customer.
        event_type:         e.g. "Birthday" — shown in the order.
        event_date:         e.g. "2026-05-10" — shown in the order.
        kitchen_booked:     True if Kitchen is in the booking (€300 deposit).

    Returns:
        dict with keys:
            draft_order_id  — Shopify draft order ID (integer)
            payment_url     — The invoice URL to send to the client in chat
            amount_eur      — Deposit amount as a string, e.g. "50.00"
    """
    amount      = get_deposit_amount(kitchen_booked)
    kitchen_note = " + Kitchen deposit (€250)" if kitchen_booked else ""
    description = f"Sauvage booking deposit — {event_type} on {event_date}{kitchen_note}"

    # Split name into first/last (best effort)
    name_parts  = client_name.strip().split(" ", 1)
    first_name  = name_parts[0]
    last_name   = name_parts[1] if len(name_parts) > 1 else ""

    payload = {
        "draft_order": {
            "line_items": [
                {
                    "title":    "Sauvage Booking Deposit",
                    "price":    amount,
                    "quantity": 1,
                    "taxable":  False,   # VAT already included in the quoted price
                    "properties": [
                        {"name": "Event Type",    "value": event_type},
                        {"name": "Event Date",    "value": event_date},
                        {"name": "Airtable ID",   "value": airtable_record_id},
                    ],
                }
            ],
            "customer": {
                "email":      client_email,
                "first_name": first_name,
                "last_name":  last_name,
            },
            "use_customer_default_address": False,
            "note": description,
            # Tags used by the webhook to locate the Airtable record
            "tags": f"sauvage-booking,airtable-{airtable_record_id}",
            "note_attributes": [
                {"name": "airtable_record_id", "value": airtable_record_id},
                {"name": "session_id",         "value": session_id},
                {"name": "event_type",         "value": event_type},
                {"name": "event_date",         "value": event_date},
            ],
        }
    }

    resp = requests.post(
        f"{_base_url()}/draft_orders.json",
        headers=_headers(),
        json=payload,
    )

    if resp.status_code not in (200, 201, 202):
        raise RuntimeError(
            f"Failed to create Shopify draft order: {resp.status_code}\n{resp.text}"
        )

    data          = resp.json()["draft_order"]
    draft_order_id = data["id"]
    invoice_url    = data["invoice_url"]

    return {
        "draft_order_id": draft_order_id,
        "payment_url":    invoice_url,
        "amount_eur":     amount,
    }


def get_draft_order(draft_order_id: int) -> dict:
    """Retrieve a draft order by ID."""
    resp = requests.get(
        f"{_base_url()}/draft_orders/{draft_order_id}.json",
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json()["draft_order"]


def cancel_draft_order(draft_order_id: int) -> dict:
    """Cancel a draft order (e.g. if client abandons after quote stage)."""
    resp = requests.delete(
        f"{_base_url()}/draft_orders/{draft_order_id}.json",
        headers=_headers(),
    )
    resp.raise_for_status()
    return {"status": "cancelled", "draft_order_id": draft_order_id}
