"""
stripe_webhook.py
-----------------
Flask webhook handler for Stripe payment events.

On checkout.session.completed:
  - Confirms booking in Airtable
  - Generates invoice PDF
  - Sends branded confirmation email
  - Creates Google Calendar event
  - Sends Telegram notification to hosting group

On checkout.session.expired:
  - Reverts Airtable status back to deposit_pending

Environment variables:
  STRIPE_WEBHOOK_SECRET  — whsec_... from Stripe dashboard webhook settings
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

import stripe
from flask import Blueprint, request, jsonify

stripe.api_key           = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET    = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_WEBHOOK_SECRET_2  = os.getenv("STRIPE_WEBHOOK_SECRET_2", "")

# ── Optional integrations ────────────────────────────────────────────────────
_AIRTABLE_ENABLED = False
_GCAL_WRITE       = False
_TG_ENABLED       = False

try:
    from airtable_client import confirm_booking, update_inquiry, mark_deposit_pending
    _AIRTABLE_ENABLED = True
except Exception as e:
    print(f"[StripeWebhook] Airtable not available: {e}")

try:
    from google_calendar_write import (
        create_booking as _gcal_create,
        create_booking_series as _gcal_series,
    )
    _GCAL_WRITE = True
    print("[StripeWebhook] Google Calendar write loaded ✓")
except Exception as e:
    print(f"[StripeWebhook] Calendar not available: {e}")

try:
    from telegram_notify import (
        notify_booking_confirmed as _tg_notify,
        notify_payment_failed    as _tg_failed,
    )
    _TG_ENABLED = True
except Exception as e:
    print(f"[StripeWebhook] Telegram not available: {e}")

stripe_bp = Blueprint("stripe_webhook", __name__)

_DB_PATH = os.path.join(os.path.dirname(__file__), "sessions.db")


# ── Session helpers ───────────────────────────────────────────────────────────

def _get_session_state(session_id: str) -> dict:
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
        print(f"[StripeWebhook] Session state lookup error: {e}")
        return {}


def _set_payment_confirmed(session_id: str) -> None:
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
        print(f"[StripeWebhook] payment_confirmed set for session {session_id}")
    except Exception as e:
        print(f"[StripeWebhook] _set_payment_confirmed error: {e}")


def _build_dt(date_val, time_str: str) -> Optional[datetime]:
    try:
        if isinstance(date_val, list):
            date_val = date_val[0]
        date_str = str(date_val).strip()
        time_str = str(time_str).strip()
        if date_str and time_str:
            return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except Exception as e:
        print(f"[StripeWebhook] _build_dt error: {e}")
    return None


# ── Main webhook endpoint ────────────────────────────────────────────────────

@stripe_bp.route("/stripe/webhook", methods=["POST"])
def handle_stripe_webhook():
    payload   = request.get_data()
    sig       = request.headers.get("Stripe-Signature", "")

    # Verify signature — try both secrets (snapshot + thin destinations)
    event = None
    secrets = [s for s in [STRIPE_WEBHOOK_SECRET, STRIPE_WEBHOOK_SECRET_2] if s]
    for secret in secrets:
        try:
            event = stripe.Webhook.construct_event(payload, sig, secret)
            break
        except stripe.error.SignatureVerificationError:
            continue
        except Exception as e:
            print(f"[StripeWebhook] Webhook parse error: {e}")
            return jsonify({"error": "Bad request"}), 400
    if event is None:
        print("[StripeWebhook] Invalid signature — no matching secret")
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event["type"]
    print(f"[StripeWebhook] {event_type}")

    # ── Payment completed ─────────────────────────────────────────────────────
    if event_type == "checkout.session.completed":
        cs        = event["data"]["object"]
        meta      = cs.get("metadata", {})
        record_id = meta.get("airtable_record_id", "")
        session_id = meta.get("session_id", "")
        payment_type = meta.get("payment_type", "deposit")
        amount_total = cs.get("amount_total", 0)          # cents
        amount_eur   = f"{amount_total / 100:.2f}"
        stripe_id    = cs.get("id", "")

        client_name = meta.get("client_name", "")
        event_type_b = meta.get("event_type", "Event")
        event_date   = meta.get("event_date", "")
        rooms_str    = meta.get("rooms", "")
        rooms        = [r.strip() for r in rooms_str.split(",") if r.strip()]

        if not record_id:
            print(f"[StripeWebhook] WARNING: No airtable_record_id in session {stripe_id}")
            return jsonify({"status": "skipped — no record ID"}), 200

        # 1. Update Airtable
        if _AIRTABLE_ENABLED:
            try:
                confirm_booking(record_id)
                airtable_fields = {
                    "Stripe Payment Reference": stripe_id,
                    "Deposit Collected":        True,
                    "Booking Status":           "confirmed",
                }
                if payment_type == "full_payment":
                    airtable_fields["Paid In Full"] = True
                    airtable_fields["Balance Due"]  = 0
                update_inquiry(record_id, airtable_fields)
                print(f"[StripeWebhook] Airtable confirmed: {record_id}")
            except Exception as e:
                print(f"[StripeWebhook] Airtable update failed: {e}")

        # 2. Mark session as paid
        _set_payment_confirmed(session_id)

        # 3. Build email state from session
        email_state = _get_session_state(session_id) if session_id else {}
        if not email_state.get("email"):
            email_state["email"] = cs.get("customer_details", {}).get("email", "")
        if not email_state.get("client_name"):
            email_state["client_name"] = client_name

        # 4. Generate invoice PDF
        inv_num = inv_pdf = inv_url_str = ""
        try:
            from invoice_generator import build_invoice, save_invoice, invoice_url as _inv_url
            deposit_paid = float(amount_eur)
            inv_num, inv_pdf = build_invoice(
                email_state,
                deposit_paid = deposit_paid,
                record_id    = record_id,
            )
            save_invoice(inv_num, inv_pdf)
            inv_url_str = _inv_url(inv_num)
            if _AIRTABLE_ENABLED:
                update_inquiry(record_id, {
                    "Invoice Number": inv_num,
                    "Invoice URL":    inv_url_str,
                })
            print(f"[StripeWebhook] Invoice {inv_num} → {inv_url_str}")
        except Exception as e:
            print(f"[StripeWebhook] Invoice generation failed (non-fatal): {e}")

        # 5. Send confirmation email
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
            print(f"[StripeWebhook] Confirmation email failed: {e}")

        # 6. Google Calendar event
        cal_link = ""
        if _GCAL_WRITE:
            try:
                st          = email_state
                dates_val   = st.get("dates") or event_date
                start_time  = st.get("start_time", "")
                end_time    = st.get("end_time", "")
                arrival_time = st.get("arrival_time", "")
                cal_rooms   = st.get("rooms") or rooms
                if isinstance(cal_rooms, str):
                    cal_rooms = [cal_rooms]

                common_kwargs = dict(
                    client_name  = st.get("client_name") or client_name,
                    event_type   = st.get("event_type")  or event_type_b,
                    rooms        = cal_rooms,
                    guest_count  = st.get("guest_count", 0),
                    email        = st.get("email", ""),
                    phone        = st.get("phone", ""),
                    airtable_id  = record_id,
                    arrival_time = arrival_time,
                )

                if isinstance(dates_val, list) and len(dates_val) >= 2 and start_time and end_time:
                    events   = _gcal_series(dates=dates_val, start_time_str=start_time,
                                            end_time_str=end_time, **common_kwargs)
                    cal_link = events[0].get("htmlLink", "") if events else ""
                elif start_time and end_time:
                    start = _build_dt(dates_val, start_time)
                    end   = _build_dt(dates_val, end_time)
                    if start and end:
                        ev = _gcal_create(start_dt=start, end_dt=end, **common_kwargs)
                        cal_link = ev.get("htmlLink", "")

                if cal_link and _AIRTABLE_ENABLED:
                    update_inquiry(record_id, {"Calendar Link": cal_link})

            except Exception as e:
                print(f"[StripeWebhook] Calendar write error: {e}")

        # 7. Telegram notification
        if _TG_ENABLED:
            try:
                _tg_notify(
                    client_name    = email_state.get("client_name", client_name),
                    event_type     = email_state.get("event_type",  event_type_b),
                    event_date     = event_date,
                    start_time     = email_state.get("start_time", ""),
                    end_time       = email_state.get("end_time",   ""),
                    guest_count    = email_state.get("guest_count", 0),
                    rooms          = email_state.get("rooms") or rooms,
                    deposit_amount = amount_eur,
                    order_number   = stripe_id,
                    airtable_id    = record_id,
                    cal_link       = cal_link,
                    state          = email_state,
                )
            except Exception as e:
                print(f"[StripeWebhook] Telegram notification failed (non-fatal): {e}")

    # ── Payment failed ────────────────────────────────────────────────────────
    elif event_type == "payment_intent.payment_failed":
        pi        = event["data"]["object"]
        meta      = pi.get("metadata", {})
        record_id = meta.get("airtable_record_id", "")
        pi_id     = pi.get("id", "")
        amount_eur = f"{pi.get('amount', 0) / 100:.2f}"

        # Extract failure reason
        last_err = pi.get("last_payment_error") or {}
        reason   = last_err.get("message") or last_err.get("code") or "Payment failed"

        print(f"[StripeWebhook] Payment failed: {pi_id} — {reason}")

        if _TG_ENABLED:
            try:
                _tg_failed(
                    client_name    = meta.get("client_name", ""),
                    event_type     = meta.get("event_type",  ""),
                    event_date     = meta.get("event_date",  ""),
                    amount_eur     = amount_eur,
                    failure_reason = reason,
                    stripe_pi_id   = pi_id,
                    airtable_id    = record_id,
                )
            except Exception as e:
                print(f"[StripeWebhook] Telegram failure alert error: {e}")

    # ── Session expired (client abandoned) ───────────────────────────────────
    elif event_type == "checkout.session.expired":
        cs        = event["data"]["object"]
        meta      = cs.get("metadata", {})
        record_id = meta.get("airtable_record_id", "")
        if record_id and _AIRTABLE_ENABLED:
            try:
                update_inquiry(record_id, {
                    "Booking Status": "deposit_pending",
                    "Notes": f"Stripe checkout expired: {cs.get('id', '')}",
                })
                print(f"[StripeWebhook] Checkout expired — Airtable reverted: {record_id}")
            except Exception as e:
                print(f"[StripeWebhook] Airtable revert failed: {e}")

    return jsonify({"status": "ok"}), 200
