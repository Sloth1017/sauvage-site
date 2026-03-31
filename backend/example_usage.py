"""
example_usage.py
----------------
Shows how to wire airtable_client.py into your Sauvage chatbot.

This mirrors the actual conversation flow from the system prompt:
  Stage 1 → event type captured
  Stage 2 → date/time captured
  Stage 3 → contact details captured
  Stage 4 → rooms selected
  Stage 5 → add-ons discussed
  Stage 6 → quote presented
  Stage 7 → deposit link sent
  Stage 8 → payment confirmed

In your real chatbot, replace the hardcoded values below with data
extracted from the conversation by your LLM.
"""

import uuid
from airtable_client import (
    create_inquiry,
    advance_stage,
    save_contact_details,
    save_rooms_and_date,
    save_addons,
    save_quote,
    mark_deposit_pending,
    confirm_booking,
    save_attribution,
    update_inquiry,
    mark_abandoned,
    snapshot_session,
    restore_session_snapshot,
    add_to_waitlist,
    notify_next_on_waitlist,
    is_date_available,
    get_inquiry_by_session,
)


# ---------------------------------------------------------------------------
# Each user conversation gets a unique session_id.
# Store this in your session/memory object alongside the Airtable record_id.
# ---------------------------------------------------------------------------

def run_example_booking_flow():
    session_id = str(uuid.uuid4())
    print(f"Session: {session_id}\n")

    # ------------------------------------------------------------------
    # STAGE 1 — Client states event type
    # ------------------------------------------------------------------
    print("Stage 1: client says 'I want to host a birthday party'")
    record_id = create_inquiry(session_id, event_type="Birthday")
    print(f"  → Airtable record created: {record_id}\n")

    # ------------------------------------------------------------------
    # STAGE 2 — Date and time
    # ------------------------------------------------------------------
    requested_date = "2026-05-10"
    print(f"Stage 2: client says they want {requested_date}, evening")

    if not is_date_available(requested_date):
        print(f"  → Date unavailable! Offering alternatives or waitlist.")
        # Waitlist path — see run_example_waitlist_flow() below
        return

    advance_stage(record_id, "2_date_time", {
        "Requested Date": requested_date,
        "Time Slot":      "16:00-00:00",
        "Duration":       "Half-Day",
    })
    print("  → Date available, stage updated to 2_date_time\n")

    # ------------------------------------------------------------------
    # STAGE 3 — Contact details
    # ------------------------------------------------------------------
    print("Stage 3: client provides name, email, phone")
    save_contact_details(
        record_id,
        name="Anna de Boer",
        email="anna@example.com",
        phone="+31612345678",
        customer_type="Private",
    )
    print("  → Contact saved\n")

    # Save a session snapshot so the conversation can be resumed on drop-off
    snapshot_session(record_id, {
        "stage":        "3_contact",
        "name":         "Anna de Boer",
        "event_type":   "Birthday",
        "date":         requested_date,
    })

    # ------------------------------------------------------------------
    # STAGE 4 — Rooms
    # ------------------------------------------------------------------
    print("Stage 4: client picks Upstairs + Cave")
    save_rooms_and_date(
        record_id,
        rooms=["Upstairs (Gallery)", "Cave"],
        requested_date=requested_date,
        time_slot="16:00-00:00",
        duration="Half-Day",
        guest_count=18,
        booking_block="Single Day",
    )
    print("  → Rooms saved\n")

    # ------------------------------------------------------------------
    # STAGE 5 — Add-ons + special flags
    # ------------------------------------------------------------------
    print("Stage 5: client wants glassware, client mentions music")
    save_addons(
        record_id,
        addons=["Glassware (25 pax)"],
        special_flags=["Music Requested"],
    )
    print("  → Add-ons saved\n")

    # ------------------------------------------------------------------
    # STAGE 6 — Quote
    # Upstairs Half-Day €70 + Cave Half-Day €100 = €170
    # 2-room bundle discount 20% = -€34 → rooms subtotal €136
    # Glassware €25 → total €161 incl VAT
    # VAT 21%: incl = 161, ex = 133.06, vat = 27.94
    # ------------------------------------------------------------------
    print("Stage 6: presenting quote")
    total_incl_vat = 161.00
    total_ex_vat   = round(total_incl_vat / 1.21, 2)
    vat_amount     = round(total_incl_vat - total_ex_vat, 2)
    save_quote(
        record_id,
        total_incl_vat=total_incl_vat,
        total_ex_vat=total_ex_vat,
        vat_amount=vat_amount,
        deposit_amount=50.00,
        bundle_discount_pct=20,
        closure_premiums_applied=False,
    )
    print(f"  → Quote saved: €{total_incl_vat} incl VAT, deposit €50\n")

    # ------------------------------------------------------------------
    # STAGE 7 — Generate Stripe Checkout link and send to client
    # ------------------------------------------------------------------
    print("Stage 7: client confirms quote, generating Stripe Checkout link")
    from shopify_client import create_checkout_session

    kitchen_booked = "Kitchen" in ["Upstairs (Gallery)", "Cave"]  # False in this example
    checkout = create_checkout_session(
        airtable_record_id=record_id,
        client_email="anna@example.com",
        client_name="Anna de Boer",
        event_type="Birthday",
        event_date=requested_date,
        kitchen_booked=kitchen_booked,
    )
    payment_url = checkout["payment_url"]
    session_id  = checkout["session_id"]
    amount_eur  = checkout["amount_eur"]

    print(f"  → Stripe session created: {session_id}")
    print(f"  → Deposit: €{amount_eur:.2f}")
    print(f"  → Payment URL: {payment_url}")
    print(f"  → Send this URL to the client in chat\n")

    # Update Airtable with the Stripe session ID and mark deposit pending
    mark_deposit_pending(record_id, stripe_payment_reference=session_id)
    print("  → Airtable updated: deposit_pending\n")

    # ------------------------------------------------------------------
    # STAGE 8 — Payment confirmed (triggered by Stripe webhook, not manually)
    # ------------------------------------------------------------------
    # In production this step happens automatically via stripe_webhook.py.
    # The webhook receives checkout.session.completed from Stripe and calls
    # confirm_booking(record_id) on its own.
    #
    # You do NOT need to call this manually — it's shown here for clarity only.
    print("Stage 8: (in production, shopify_webhook.py handles this automatically)")
    print("  → On orders/paid: confirm_booking(record_id) + Airtable updated to confirmed\n")

    # ------------------------------------------------------------------
    # ATTRIBUTION — collected near end of conversation
    # ------------------------------------------------------------------
    print("Attribution: client says 'I heard about you from Dorian'")
    save_attribution(
        record_id,
        referral_source="Dorian",
        attributed_host="Dorian",
    )
    print("  → Attribution saved\n")

    print(f"Done. View record in Airtable: record ID = {record_id}")


# ---------------------------------------------------------------------------
# WAITLIST FLOW
# ---------------------------------------------------------------------------

def run_example_waitlist_flow():
    """Called when a client requests a date that's already taken."""
    print("Waitlist example\n")

    waitlist_id = add_to_waitlist(
        client_name="Bas Vink",
        email="bas@example.com",
        phone="+31698765432",
        requested_date="2026-05-10",
        event_type="Corporate",
        rooms_interested=["Kitchen", "Entrance"],
        guest_count=20,
        notes="Needs Kitchen for catering demo",
    )
    print(f"  → Waitlist record created: {waitlist_id}")

    # Later — cancellation occurs on 2026-05-10
    print("\nSimulating cancellation on 2026-05-10...")
    next_client = notify_next_on_waitlist("2026-05-10")
    if next_client:
        name  = next_client["fields"].get("Client Name")
        email = next_client["fields"].get("Email")
        phone = next_client["fields"].get("Phone")
        print(f"  → Notifying: {name} ({email} / {phone})")
        print("     Send: 'Good news — a spot has just opened up at Sauvage on May 10!'")
    else:
        print("  → No one on the waitlist.")


# ---------------------------------------------------------------------------
# ABANDONED CONVERSATION HANDLER
# Called by your background job (e.g. cron every hour)
# ---------------------------------------------------------------------------

def handle_abandoned_conversations():
    """
    Pseudocode pattern — adapt to your scheduler.
    In Make.com or n8n, you'd query Airtable directly with an automation.
    Here's the logic if you're doing it in Python.
    """
    from pyairtable import Api
    from datetime import datetime, timedelta, timezone
    import os

    api    = Api(os.getenv("AIRTABLE_API_KEY"))
    table  = api.table(os.getenv("AIRTABLE_BASE_ID"), "Inquiries")

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # Records that are not yet confirmed or abandoned, last updated > 24h ago
    formula = (
        f"AND("
        f"  NOT({{Booking Status}} = 'confirmed'), "
        f"  NOT({{Funnel Stage}} = 'abandoned'), "
        f"  IS_BEFORE(LAST_MODIFIED_TIME(), '{cutoff}')"
        f")"
    )
    stale = table.all(formula=formula)

    for record in stale:
        record_id = record["id"]
        fields    = record["fields"]
        print(f"Marking abandoned: {fields.get('Client Name', 'Unknown')} "
              f"(stage: {fields.get('Funnel Stage')})")
        mark_abandoned(record_id, notes="Auto-abandoned after 24h inactivity")


# ---------------------------------------------------------------------------
# RESUME SESSION — for when a client returns after dropping off
# ---------------------------------------------------------------------------

def resume_conversation(session_id: str):
    """
    Look up an existing session and restore where they left off.
    Call this at the start of every new message in a conversation.
    """
    existing = get_inquiry_by_session(session_id)
    if not existing:
        return None  # New conversation

    record_id = existing["id"]
    stage     = existing["fields"].get("Funnel Stage")
    snapshot  = restore_session_snapshot(record_id)

    print(f"Resuming session {session_id}")
    print(f"  Stage:    {stage}")
    print(f"  Snapshot: {snapshot}")

    return {
        "record_id": record_id,
        "stage":     stage,
        "snapshot":  snapshot,
        "fields":    existing["fields"],
    }


# ---------------------------------------------------------------------------
# Run examples
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("EXAMPLE 1: Full booking flow")
    print("=" * 60)
    run_example_booking_flow()

    print("\n" + "=" * 60)
    print("EXAMPLE 2: Waitlist flow")
    print("=" * 60)
    run_example_waitlist_flow()
