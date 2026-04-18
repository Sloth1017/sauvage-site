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
import os
import sqlite3
import requests as _requests
from datetime import datetime
from flask import Flask, Blueprint, request, jsonify
from typing import Optional

try:
    from config import SHOPIFY_WEBHOOK_SECRET
except ImportError:
    SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET")

# Separate secret for the selectionsauvage.nl Shopify store
SELECTION_SAUVAGE_WEBHOOK_SECRET = os.getenv("SELECTION_SAUVAGE_WEBHOOK_SECRET", "")

# ── Make.com / Routines webhook (optional) ────────────────────────────────────
# Set MAKE_WEBHOOK_URL in your .env to enable booking summary emails via Make.com
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "")

# ── Telegram notifications ────────────────────────────────────────────────────
try:
    from telegram_notify import notify_booking_confirmed as _tg_notify
    _TG_ENABLED = True
except Exception as _tg_err:
    _TG_ENABLED = False
    print(f"[Telegram] Not available: {_tg_err}")

def _notify_make(payload: dict) -> None:
    """POST booking summary to Make.com webhook — non-blocking, errors are logged not raised."""
    if not MAKE_WEBHOOK_URL:
        return
    try:
        r = _requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=10)
        print(f"[Make.com] Notified — status {r.status_code}")
    except Exception as e:
        print(f"[Make.com] Notification failed: {e}")

from airtable_client import confirm_booking, update_inquiry

# ── Optional Google Calendar write ───────────────────────────────────────────
_GCAL_WRITE = False
try:
    from google_calendar_write import (
        create_booking as _gcal_create,
        create_booking_series as _gcal_series,
        cancel_booking as _gcal_cancel,
    )
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


_DB_PATH = os.path.join(os.path.dirname(__file__), "sessions.db")

def _get_session_state(session_id: str) -> dict:
    """Read booking state directly from the SQLite sessions DB."""
    if not session_id:
        return {}
    try:
        conn = sqlite3.connect(_DB_PATH)
        row  = conn.execute(
            "SELECT state FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        conn.close()
        return json.loads(row[0]) if row else {}
    except Exception as e:
        print(f"[Webhook] Session state lookup error: {e}")
        return {}

def _set_payment_confirmed(session_id: str) -> None:
    """Mark payment as confirmed in the session meta so Claude stops showing deposit link."""
    if not session_id:
        return
    try:
        conn = sqlite3.connect(_DB_PATH)
        row  = conn.execute(
            "SELECT meta FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        meta = json.loads(row[0]) if row else {}
        meta["payment_confirmed"] = True
        conn.execute(
            "UPDATE sessions SET meta = ?, updated_at = unixepoch() WHERE session_id = ?",
            (json.dumps(meta), session_id)
        )
        conn.commit()
        conn.close()
        print(f"[Webhook] payment_confirmed set for session {session_id}")
    except Exception as e:
        print(f"[Webhook] _set_payment_confirmed error: {e}")

def _build_dt(date_val, time_str: str) -> Optional[datetime]:
    """Combine a date (ISO string or list) and HH:MM time into a datetime."""
    try:
        if isinstance(date_val, list):
            date_val = date_val[0]
        date_str = str(date_val).strip()
        time_str = str(time_str).strip()
        if date_str and time_str:
            return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except Exception as e:
        print(f"[Webhook] _build_dt error: {e}")
    return None

def _extract_session_id(order: dict) -> Optional[str]:
    attrs = {a["name"]: a["value"] for a in order.get("note_attributes", [])}
    return attrs.get("session_id")

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
        details = extract_booking_details(order)
        update_inquiry(record_id, {
            "Stripe Payment Reference": f"shopify-order-{order_number}",
            "Deposit Collected":        True,
            "Booking Status":           "confirmed",
        })
        print(f"[Webhook] Airtable confirmed: {record_id}")

        # Mark session so Claude stops showing deposit link
        session_id_main = _extract_session_id(order)
        _set_payment_confirmed(session_id_main)

        # 1b. Build email state (used for invoice + email)
        email_state = _get_session_state(session_id_main) if session_id_main else {}
        if not email_state.get("email"):
            email_state["email"] = details.get("email", "")
        if not email_state.get("client_name"):
            email_state["client_name"] = details.get("client_name", "")

        # 2. Generate invoice PDF
        inv_num = inv_pdf = inv_url_str = ""
        try:
            from invoice_generator import build_invoice, save_invoice, invoice_url as _inv_url
            deposit_paid = float(amount_total or 0)
            inv_num, inv_pdf = build_invoice(
                email_state,
                deposit_paid = deposit_paid,
                record_id    = record_id,
            )
            save_invoice(inv_num, inv_pdf)
            inv_url_str = _inv_url(inv_num)
            # Write invoice number + URL to Airtable
            update_inquiry(record_id, {
                "Invoice Number": inv_num,
                "Invoice URL":    inv_url_str,
            })
            print(f"[Webhook] Invoice {inv_num} generated → {inv_url_str}")
        except Exception as e:
            print(f"[Webhook] Invoice generation failed (non-fatal): {e}")

        # 3. Send branded confirmation email (with PDF attached)
        try:
            from confirmation_email import send_booking_confirmation
            send_booking_confirmation(
                record_id,
                email_state,
                invoice_pdf    = inv_pdf or None,
                invoice_number = inv_num,
                invoice_url    = inv_url_str,
            )
        except Exception as e:
            print(f"[Webhook] Confirmation email failed: {e}")

        # 3. Notify Make.com — sends summary email to client + Sauvage team
        _notify_make({
            "event":          "booking_confirmed",
            "order_number":   order_number,
            "airtable_id":    record_id,
            "client_name":    details["client_name"],
            "client_email":   details["email"],
            "client_phone":   details["phone"],
            "event_type":     details["event_type"],
            "event_date":     details.get("event_date", ""),
            "start_time":     details["start_dt"],
            "end_time":       details["end_dt"],
            "guest_count":    details["guest_count"],
            "rooms":          details["rooms"],
            "deposit_amount": amount_total,
            "airtable_url":   f"https://airtable.com/appXXXXXXXX/tblXXXXXXXX/{record_id}",
        })

        # 4. Create Google Calendar event — use session state for full booking data
        if _GCAL_WRITE:
            try:
                session_id = _extract_session_id(order)
                st = _get_session_state(session_id) if session_id else {}

                dates_val    = st.get("dates") or details.get("start_dt", "")
                start_time   = st.get("start_time", "")
                end_time     = st.get("end_time",   "")
                arrival_time = st.get("arrival_time", "")

                rooms = st.get("rooms") or details.get("rooms", [])
                if isinstance(rooms, str):
                    rooms = [rooms]

                common_kwargs = dict(
                    client_name  = st.get("client_name")  or details["client_name"],
                    event_type   = st.get("event_type")   or details["event_type"],
                    rooms        = rooms,
                    guest_count  = st.get("guest_count")  or details["guest_count"],
                    email        = st.get("email")        or details["email"],
                    phone        = st.get("phone")        or details["phone"],
                    airtable_id  = record_id,
                    arrival_time = arrival_time,
                )

                # Multi-day: create one event per date
                if isinstance(dates_val, list) and len(dates_val) >= 2 and start_time and end_time:
                    events = _gcal_series(
                        dates          = dates_val,
                        start_time_str = start_time,
                        end_time_str   = end_time,
                        **common_kwargs,
                    )
                    cal_link = events[0].get("htmlLink", "") if events else ""
                    print(f"[Webhook] Calendar series created: {len(events)} events, first: {cal_link}")

                # Single day
                elif start_time and end_time:
                    start = _build_dt(dates_val, start_time)
                    end   = _build_dt(dates_val, end_time)
                    if start and end:
                        ev = _gcal_create(start_dt=start, end_dt=end, **common_kwargs)
                        cal_link = ev.get("htmlLink", "")
                        print(f"[Webhook] Calendar event created: {cal_link}")
                    else:
                        cal_link = ""
                        print(f"[Webhook] Skipped calendar — could not parse datetime "
                              f"(dates={dates_val}, start={start_time}, end={end_time})")
                else:
                    cal_link = ""
                    print(f"[Webhook] Skipped calendar — missing start/end time "
                          f"(session={session_id})")

                if cal_link:
                    update_inquiry(record_id, {"Calendar Link": cal_link})

            except Exception as e:
                print(f"[Webhook] Calendar write error: {e}")
                # Non-fatal — booking is still confirmed in Airtable

        # 5. Telegram notification — Greg, Dorian, Bart
        if _TG_ENABLED:
            try:
                _tg_notify(
                    client_name          = details["client_name"],
                    event_type           = details["event_type"],
                    event_date           = details.get("event_date", ""),
                    start_time           = details["start_dt"],
                    end_time             = details["end_dt"],
                    guest_count          = details["guest_count"],
                    rooms                = details["rooms"],
                    deposit_amount       = amount_total,
                    order_number         = order_number,
                    airtable_id          = record_id,
                    cal_link             = cal_link if _GCAL_WRITE else "",
                    quote_total_inc_vat  = email_state.get("quote_total") or None,
                )
            except Exception as e:
                print(f"[Webhook] Telegram notification failed (non-fatal): {e}")

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


# ── Selection Sauvage wine order webhook ──────────────────────────────────────

@webhook_bp.route("/shopify/wines-order", methods=["POST"])
def handle_wines_order():
    payload     = request.get_data()
    hmac_header = request.headers.get("X-Shopify-Hmac-SHA256", "")
    topic       = request.headers.get("X-Shopify-Topic", "")

    # Verify using the selectionsauvage.nl store secret
    if SELECTION_SAUVAGE_WEBHOOK_SECRET:
        digest   = hmac.new(SELECTION_SAUVAGE_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).digest()
        computed = base64.b64encode(digest).decode()
        if not hmac.compare_digest(computed, hmac_header):
            return jsonify({"error": "Invalid signature"}), 401

    if topic not in ("orders/create", "orders/paid"):
        return jsonify({"status": "ignored"}), 200

    try:
        order = json.loads(payload)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON"}), 400

    customer_email = (order.get("email") or "").strip().lower()
    order_number   = str(order.get("order_number", ""))
    order_date     = order.get("created_at", "")[:10]
    total          = float(order.get("total_price", 0))

    # Build a readable summary of what was purchased
    lines = []
    for item in order.get("line_items", []):
        title    = item.get("title", "Unknown")
        variant  = item.get("variant_title") or ""
        qty      = item.get("quantity", 1)
        price    = float(item.get("price", 0)) * qty
        label    = f"{title} ({variant})" if variant and variant != "Default Title" else title
        lines.append(f"{qty}x {label} — €{price:.2f}")

    purchase_summary = "\n".join(lines) if lines else "No items"

    print(f"[WinesWebhook] Order #{order_number} from {customer_email}: {purchase_summary}")

    if not customer_email:
        return jsonify({"status": "skipped — no email"}), 200

    # Match to a confirmed Airtable booking by email
    try:
        from airtable_client import get_confirmed_inquiry_by_email, update_inquiry
        record = get_confirmed_inquiry_by_email(customer_email)
        if record:
            record_id = record["id"]
            update_inquiry(record_id, {
                "Wine Purchase":    purchase_summary,
                "Wine Order Total": round(total, 2),
                "Wine Order #":     order_number,
            })
            print(f"[WinesWebhook] Airtable updated: {record_id}")
        else:
            print(f"[WinesWebhook] No confirmed booking found for {customer_email}")
    except Exception as e:
        print(f"[WinesWebhook] Airtable update failed: {e}")

    return jsonify({"status": "ok"}), 200
