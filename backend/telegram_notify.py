"""
telegram_notify.py
------------------
Sends booking notifications to a Telegram group chat.

Setup:
  1. Create a bot via @BotFather on Telegram → get TELEGRAM_BOT_TOKEN
  2. Create a group, add your bot + Greg, Dorian, Bart
  3. Send any message in the group, then call get_chat_id() once to find TELEGRAM_CHAT_ID
  4. Set both as environment variables (or in .env / config.py)

Environment variables:
  TELEGRAM_BOT_TOKEN  — from BotFather, e.g. "7412345678:AAF..."
  TELEGRAM_CHAT_ID    — the group chat ID, e.g. "-1001234567890"
"""

import os
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "")

_API = "https://api.telegram.org/bot{token}/{method}"


def _post(method: str, **kwargs) -> dict:
    if not TELEGRAM_BOT_TOKEN:
        print("[Telegram] BOT_TOKEN not set — skipping")
        return {}
    url = _API.format(token=TELEGRAM_BOT_TOKEN, method=method)
    try:
        r = requests.post(url, json=kwargs, timeout=10)
        return r.json()
    except Exception as e:
        print(f"[Telegram] Request failed: {e}")
        return {}


def send_message(text: str, chat_id: str = None) -> dict:
    """Send a plain or HTML-formatted message to the group."""
    cid = chat_id or TELEGRAM_CHAT_ID
    if not cid:
        print("[Telegram] CHAT_ID not set — skipping")
        return {}
    return _post("sendMessage", chat_id=cid, text=text, parse_mode="HTML")


def notify_booking_confirmed(
    client_name:  str,
    event_type:   str,
    event_date:   str,
    start_time:   str,
    end_time:     str,
    guest_count,
    rooms,
    deposit_amount: str,
    order_number:   str,
    airtable_id:    str = "",
    cal_link:       str = "",
) -> None:
    """
    Fire-and-forget booking notification. Non-fatal — errors are logged only.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Not configured — skipping booking notification")
        return

    rooms_str = ", ".join(rooms) if isinstance(rooms, list) else str(rooms or "—")
    time_str  = f"{start_time} – {end_time}" if start_time and end_time else start_time or "TBC"

    lines = [
        "🍷 <b>New Booking Confirmed</b>",
        "",
        f"<b>Client:</b> {client_name}",
        f"<b>Event:</b> {event_type}",
        f"<b>Date:</b> {event_date}",
        f"<b>Time:</b> {time_str}",
        f"<b>Space:</b> {rooms_str}",
        f"<b>Guests:</b> {guest_count}",
        f"<b>Deposit:</b> €{deposit_amount}",
    ]

    if cal_link:
        lines.append(f"<b>Calendar:</b> <a href=\"{cal_link}\">View event</a>")

    if airtable_id:
        lines.append(f"<b>Airtable:</b> <a href=\"https://airtable.com/{airtable_id}\">Open record</a>")

    lines.append(f"\n<i>Order #{order_number}</i>")

    try:
        result = send_message("\n".join(lines))
        if result.get("ok"):
            print(f"[Telegram] Booking notification sent for order #{order_number}")
        else:
            print(f"[Telegram] Notification failed: {result}")
    except Exception as e:
        print(f"[Telegram] Notification error (non-fatal): {e}")


def get_chat_id() -> None:
    """
    Helper — run once to find your group chat ID after adding the bot to the group.
    Usage: python3 -c "from telegram_notify import get_chat_id; get_chat_id()"
    """
    result = _post("getUpdates")
    updates = result.get("result", [])
    if not updates:
        print("No updates yet. Send a message in your group first, then retry.")
        return
    for u in updates[-5:]:
        chat = u.get("message", {}).get("chat", {})
        print(f"Chat ID: {chat.get('id')}  Type: {chat.get('type')}  Title: {chat.get('title', chat.get('first_name', ''))}")
