"""
stripe_client.py
----------------
Creates Stripe Checkout Sessions for Sauvage booking deposits (or full payments).

Deposit tiers:
  T1 — €50   (no kitchen, single-day)
  T2 — €150  (kitchen included, single-day)
  T3 — €250  (multi-day bookings)

Full-payment rule:
  If the event is within 7 days of today, the full event total is charged
  in a single payment instead of a deposit.

Environment variables:
  STRIPE_SECRET_KEY      — sk_live_... or sk_test_...
  STRIPE_WEBHOOK_SECRET  — whsec_... (set after registering webhook in Stripe dashboard)
  BASE_URL               — https://sauvage.amsterdam
"""

import os
import stripe
from datetime import date, datetime, timedelta
from typing import Optional

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

BASE_URL = os.getenv("BASE_URL", "https://sauvage.amsterdam")

# Deposit amounts in euro cents
DEPOSIT_T1 = 5_000   # €50
DEPOSIT_T2 = 15_000  # €150
DEPOSIT_T3 = 25_000  # €250

# Days threshold for full-payment rule
FULL_PAYMENT_WINDOW_DAYS = 7


def is_within_payment_window(event_date) -> bool:
    """Return True if the event is within FULL_PAYMENT_WINDOW_DAYS from today."""
    try:
        if isinstance(event_date, list):
            event_date = event_date[0]
        if not event_date:
            return False
        if isinstance(event_date, str):
            event_date = date.fromisoformat(str(event_date)[:10])
        delta = (event_date - date.today()).days
        return 0 <= delta < FULL_PAYMENT_WINDOW_DAYS
    except Exception:
        return False


def get_deposit_tier(rooms: list, is_multiday: bool = False) -> tuple:
    """
    Returns (amount_cents, tier_label) based on rooms and booking type.
    T3 for multi-day; T2 for kitchen; T1 otherwise.
    """
    has_kitchen = any(str(r).lower() in ("kitchen", "k") for r in rooms)
    if is_multiday:
        return DEPOSIT_T3, "T3"
    if has_kitchen:
        return DEPOSIT_T2, "T2"
    return DEPOSIT_T1, "T1"


def create_checkout_session(
    airtable_record_id: str,
    client_email: str,
    client_name: str,
    event_type: str,
    event_date,
    rooms: list,
    session_id: str = "",
    full_amount_cents: Optional[int] = None,
    is_multiday: bool = False,
) -> dict:
    """
    Create a Stripe Checkout Session for the booking.

    If the event is within 7 days AND full_amount_cents is provided,
    the full event total is charged instead of a deposit.

    Returns:
        checkout_session_id  — Stripe session ID (cs_...)
        payment_url          — Checkout URL to send to the client
        amount_cents         — Amount charged in euro cents
        payment_type         — "deposit" or "full_payment"
        tier                 — "T1" / "T2" / "T3" / "full"
    """
    date_val = event_date[0] if isinstance(event_date, list) else event_date
    date_str = str(date_val or "")

    within_window = is_within_payment_window(date_val)

    if within_window and full_amount_cents and full_amount_cents > 0:
        amount_cents = full_amount_cents
        payment_type = "full_payment"
        tier         = "full"
        product_name = "Sauvage Event — Full Payment"
        description  = f"{event_type} on {date_str} · full payment (event within 7 days)"
    else:
        amount_cents, tier = get_deposit_tier(rooms, is_multiday)
        payment_type = "deposit"
        product_name = f"Sauvage Booking Deposit ({tier})"
        description  = f"{event_type} on {date_str} · deposit {tier}"

    rooms_str = ",".join(rooms) if isinstance(rooms, list) else str(rooms or "")

    session = stripe.checkout.Session.create(
        payment_method_types=["card", "ideal"],
        mode="payment",
        customer_email=client_email or None,
        line_items=[{
            "price_data": {
                "currency": "eur",
                "unit_amount": amount_cents,
                "product_data": {
                    "name": product_name,
                    "description": description,
                },
            },
            "quantity": 1,
        }],
        metadata={
            "airtable_record_id": airtable_record_id,
            "session_id":         session_id,
            "client_name":        client_name,
            "event_type":         event_type,
            "event_date":         date_str,
            "rooms":              rooms_str,
            "payment_type":       payment_type,
            "deposit_tier":       tier,
        },
        success_url=f"{BASE_URL}/?payment=success&sid={session_id}",
        cancel_url=f"{BASE_URL}/?payment=cancelled&sid={session_id}",
        expires_at=int((datetime.utcnow() + timedelta(hours=24)).timestamp()),
    )

    return {
        "checkout_session_id": session.id,
        "payment_url":         session.url,
        "amount_cents":        amount_cents,
        "payment_type":        payment_type,
        "tier":                tier,
    }
