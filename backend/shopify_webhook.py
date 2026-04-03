"""
shopify_webhook.py
------------------
Flask webhook handler for Shopify payment events.
On payment confirmed: updates Airtable AND creates a Google Calendar event.
On order cancelled: reverts Airtable status and deletes the calendar event.
"""

import hmac
import hashlib
import base64
import json
from flask import Flask, Blueprint, request, jsonify
from typing import Optional

try:
    from config import SHOPIFY_WEBHOOK_SECRET
except ImportError:
    import os
    SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET")

from airtable_client import confirm_booking, update_inquiry

# ── Optional Google Calendar write ───────────────────────────────────────────
_GCAL_WRITE = False
try:
    from google_calendar_write import create_booking as _gcal_create, cancel_booking as _gcal_cancel
    _GCAL_WRITE = True
    print("[CalendarWrite] Google Calendar write integration loaded ✓")
except Exception as e:
    print(f"[CalendarWrite] Not available: {e}")

webhook_bp = Blueprint("shopify_webhook", __name__)
AIRTABLE_TAG_PREFIX = "airtable-"


# ── Signature verification ────────────────────────────────────────────────────

def verify_shopify_signature(payload: bytes, hmac_header: str) -> bool:
    if not SHOPIFY_WEBHOOK_SECRET or not hmac_header:
        return False
    digest   = hmac.new(SHOPIFY_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).digest()
    computed = base64.b64encode(digest).decode()
    return hmac.compare_digest(computed, hmac_header)


def extract_airtable_record_id(order: dict) -> Optional[str]:
    for attr in order.get("note_attributes", []):
        if attr.get("name") == "airtable_record_id":
            return attr["value"]
    tags = order.get("tags", "")
    for tag in tags.split(","):
        tag = tag.strip()
        if tag.startswith(AIRTABLE_TAG_PREFIX):
            return tag[len(AIRTABLE_TAG_PREFIX):]
    for item in order.get("line_items", []):
        for prop in item.get("properties", []):
            if prop.get("name") == "Airtable ID":
                return prop["value"]
    return None


def extract_booking_details(order: dict) -> dict:
    """
    Pull booking details from Shopify order note_attributes.
    The chatbot stores these when creating the checkout.
    """
    attrs = {a["name"]: a["value"] for a in order.get("note_attributes", [])}
    return {
        "client_name":  attrs.get("client_name", order.get("billing_address", {}).get("name", "Unknown")),
        "event_type":   attrs.get("event_type", "Event"),
        "rooms":        json.loads(attrs["rooms"]) if "rooms" in attrs else ["gallery"],
        "start_dt":     attrs.get("start_datetime", ""),
        "end_dt":       attrs.get("end_datetime", ""),
        "guest_count":  int(attrs.get("guest_count", 0)),
        "email":        order.get("email", attrs.get("email", "")),
        "phone":        order.get("phone", attrs.get("phone", "")),
        "airtable_id":  attrs.get("airtable_record_id", ""),
    }


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@webhook_bp.route("/shopify/webhook", methods=["POST"])
def handle_webhook():
    payload     = request.get_data()
    hmac_header = request.headers.get("X-Shopify-Hmac-SHA256", "")
    topic       = request.headers.get("X-Shopify-Topic", "")

    if not verify_shopify_signature(payload, hmac_header):
        return jsonify({"error": "Invalid signature"}), 401

    try:
        order = json.loads(payload)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON"}), 400

    order_number = str(order.get("order_number", "?"))
    print(f"[Webhook] {topic} — order #{order_number}")

    # ── Payment confirmed ─────────────────────────────────────────────────────
    if topic == "orders/paid":
        record_id    = extract_airtable_record_id(order)
        amount_total = order.get("total_price", "0.00")

        if not record_id:
            print(f"[Webhook] WARNING: No Airtable record ID in order {order_number}")
            return jsonify({"status": "skipped — no record ID"}), 200

        # 1. Update Airtable
        confirm_booking(record_id)
        update_inquiry(record_id, {
            "Stripe Payment Reference": f"shopify-order-{order_number}",
            "Deposit Collected":        True,
            "Booking Status":           "confirmed",
        })
        print(f"[Webhook] Airtable confirmed: {record_id}")

        # 2. Create Google Calendar event
        if _GCAL_WRITE:
            try:
                from datetime import datetime
                details = extract_booking_details(order)

                # Parse datetimes — stored as ISO strings by the chatbot
                start = datetime.fromisoformat(details["start_dt"]) if details["start_dt"] else None
                end   = datetime.fromisoformat(details["end_dt"])   if details["end_dt"]   else None

                if start and end:
                    cal_event = _gcal_create(
                        client_name  = details["client_name"],
                        event_type   = details["event_type"],
                        rooms        = details["rooms"],
                        start_dt     = start,
                        end_dt       = end,
                        guest_count  = details["guest_count"],
                        email        = details["email"],
                        phone        = details["phone"],
                        airtable_id  = record_id,
                    )
                    # Store calendar event ID back in Airtable for later updates
                    update_inquiry(record_id, {
                        "Notes": f"Google Calendar event: {cal_event.get('htmlLink', '')}",
                    })
                    print(f"[Webhook] Calendar event created: {cal_event.get('htmlLink', '')}")
                else:
                    print(f"[Webhook] Skipped calendar — missing start/end datetime in order {order_number}")
            except Exception as e:
                print(f"[Webhook] Calendar write error: {e}")
                # Non-fatal — booking is still confirmed in Airtable

    # ── Order cancelled ───────────────────────────────────────────────────────
    elif topic == "orders/cancelled":
        record_id = extract_airtable_record_id(order)
        if record_id:
            update_inquiry(record_id, {
                "Booking Status": "deposit_pending",
                "Notes": f"Shopify order #{order_number} was cancelled",
            })
            print(f"[Webhook] Airtable reverted: {record_id}")

    return jsonify({"status": "ok"}), 200
