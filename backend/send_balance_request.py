"""
send_balance_request.py
-----------------------
Daily cron script — sends balance payment requests for confirmed
bookings that have an outstanding balance due.

Schedule:
  - T-7 days: initial balance request
  - T-2 days: reminder (if still unpaid)

Run daily at 9am Amsterdam (7am UTC):
  0 7 * * * /var/www/sauvage/venv/bin/python /root/sauvage/backend/send_balance_request.py >> /root/sauvage/backend/balance_requests.log 2>&1
"""

import os
import sys
from datetime import date, timedelta

# ── Load .env ─────────────────────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

REMINDER_DAYS = [7, 2]   # T-7 initial request, T-2 reminder
BASE_URL = os.getenv("BASE_URL", "https://sauvage.amsterdam")


def get_bookings_needing_balance() -> list:
    """Return confirmed bookings with outstanding balance due in 2 or 7 days."""
    try:
        from airtable_client import _get_table, INQUIRIES_TABLE
        table = _get_table(INQUIRIES_TABLE)

        target_dates = [
            (date.today() + timedelta(days=d)).isoformat()
            for d in REMINDER_DAYS
        ]
        date_conditions = ", ".join(
            f"{{Requested Date}} = '{d}'" for d in target_dates
        )
        formula = (
            f"AND("
            f"  {{Booking Status}} = 'confirmed', "
            f"  OR({date_conditions}), "
            f"  NOT({{Paid In Full}}), "
            f"  {{Balance Due}} > 0, "
            f"  {{Email}} != '' "
            f")"
        )
        return table.all(formula=formula)
    except Exception as e:
        print(f"[BalanceRequest] Airtable query failed: {e}")
        return []


def days_until(event_date_str: str) -> int:
    try:
        return (date.fromisoformat(str(event_date_str)[:10]) - date.today()).days
    except Exception:
        return -1


def run():
    from airtable_client import update_inquiry
    records = get_bookings_needing_balance()
    if not records:
        print("[BalanceRequest] No outstanding balances in reminder window")
        return

    for rec in records:
        fields      = rec.get("fields", {})
        record_id   = rec.get("id", "")
        client_name = fields.get("Name", "there")
        client_email = fields.get("Email", "")
        event_type  = fields.get("Event Type", "Event")
        event_date  = fields.get("Requested Date", "")
        start_time  = fields.get("Start Time", "")
        end_time    = fields.get("End Time", "")
        rooms_raw   = fields.get("Rooms", [])
        rooms       = rooms_raw if isinstance(rooms_raw, list) else [rooms_raw]
        guest_count = fields.get("Guest Count", "")
        balance_due = float(fields.get("Balance Due", 0) or 0)
        total_inc   = float(fields.get("Total Incl VAT", 0) or 0)
        deposit_paid = round(total_inc - balance_due, 2)
        d_until     = days_until(event_date)

        if balance_due <= 0:
            continue
        if not client_email:
            print(f"[BalanceRequest] No email for {record_id} — skipping")
            continue

        balance_eur  = f"{balance_due:.2f}"
        total_eur    = f"{total_inc:.2f}"
        deposit_eur  = f"{deposit_paid:.2f}"

        # ── Create Stripe checkout session for balance ────────────────────────
        payment_url = ""
        try:
            import stripe
            stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
            from datetime import datetime
            session = stripe.checkout.Session.create(
                payment_method_types=["card", "ideal"],
                mode="payment",
                customer_email=client_email or None,
                line_items=[{
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": int(balance_due * 100),
                        "product_data": {
                            "name": f"Sauvage Balance — {event_type}",
                            "description": f"{event_type} on {event_date} · remaining balance",
                        },
                    },
                    "quantity": 1,
                }],
                metadata={
                    "airtable_record_id": record_id,
                    "client_name":        client_name,
                    "event_type":         event_type,
                    "event_date":         event_date,
                    "payment_type":       "balance",
                },
                success_url=f"{BASE_URL}/?payment=success",
                cancel_url=f"{BASE_URL}/?payment=cancelled",
                expires_at=int((datetime.utcnow() + timedelta(hours=48)).timestamp()),
            )
            payment_url = session.url
            print(f"[BalanceRequest] Stripe session created: {session.id}")
        except Exception as e:
            print(f"[BalanceRequest] Stripe session failed for {record_id}: {e}")
            continue

        # ── Send email ────────────────────────────────────────────────────────
        try:
            from balance_email import send_balance_request
            sent = send_balance_request(
                record_id    = record_id,
                client_name  = client_name,
                client_email = client_email,
                event_type   = event_type,
                event_date   = event_date,
                start_time   = start_time,
                end_time     = end_time,
                rooms        = rooms,
                guest_count  = guest_count,
                balance_eur  = balance_eur,
                total_eur    = total_eur,
                deposit_eur  = deposit_eur,
                payment_url  = payment_url,
                days_until   = d_until,
            )
        except Exception as e:
            print(f"[BalanceRequest] Email failed for {record_id}: {e}")
            continue

        # ── Mark in Airtable that balance email was sent ──────────────────────
        if sent:
            try:
                label = "T-7 initial" if d_until == 7 else "T-2 reminder"
                update_inquiry(record_id, {
                    "Balance Email Sent": f"{label} — {date.today().isoformat()}",
                })
            except Exception as e:
                print(f"[BalanceRequest] Airtable update failed (non-fatal): {e}")

        # ── Telegram alert to hosting group ──────────────────────────────────
        try:
            from telegram_notify import send_message
            label = "T-7" if d_until == 7 else "T-2 reminder"
            send_message(
                f"💶 <b>Balance request sent [{label}]</b>\n"
                f"👤 {client_name} · {event_type} · {event_date}\n"
                f"Amount: €{balance_eur}"
            )
        except Exception as e:
            print(f"[BalanceRequest] Telegram alert failed (non-fatal): {e}")


if __name__ == "__main__":
    run()
