"""
telegram_notify.py
------------------
Sends interactive booking notifications to a Telegram group.

On each confirmed booking:
  • Posts a message with full event details + price breakdown (ex/inc VAT + host earnings)
  • Inline buttons: Greg 🙋 / Dorian 🙋 / Bart 🙋
  • Whoever taps first claims the hosting slot — message updates + Airtable "Host" field written

Revenue logic:
  Host earns 70% of ex-VAT (VAT is a government pass-through, not real earnings)
  DAO receives 30% of ex-VAT

Setup:
  1. Create a bot via @BotFather → get TELEGRAM_BOT_TOKEN
  2. Create a group, add the bot + Greg, Dorian, Bart
  3. Send any message in the group
  4. Run: python3 -c "from telegram_notify import get_chat_id; get_chat_id()"
  5. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars
  6. Register the webhook: python3 -c "from telegram_notify import register_webhook; register_webhook()"

Environment variables:
  TELEGRAM_BOT_TOKEN  — from BotFather, e.g. "7412345678:AAF..."
  TELEGRAM_CHAT_ID    — the group chat ID, e.g. "-1001234567890"
"""

import os
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "")
BASE_URL           = os.getenv("BASE_URL", "https://sauvage.amsterdam")

_API = "https://api.telegram.org/bot{token}/{method}"

VAT_RATE   = 0.21   # Netherlands standard rate
HOST_SHARE = 0.70   # Host earns 70% of ex-VAT


# ── Internal HTTP helper ──────────────────────────────────────────────────────

def _post(method: str, **kwargs) -> dict:
    if not TELEGRAM_BOT_TOKEN:
        print("[Telegram] BOT_TOKEN not set — skipping")
        return {}
    url = _API.format(token=TELEGRAM_BOT_TOKEN, method=method)
    try:
        r = requests.post(url, json=kwargs, timeout=10)
        return r.json()
    except Exception as e:
        print(f"[Telegram] Request failed ({method}): {e}")
        return {}


# ── Price helpers ─────────────────────────────────────────────────────────────

def _fmt_eur(amount) -> str:
    try:
        return f"€{float(amount):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _price_breakdown(quote_total_inc_vat) -> dict | None:
    """Return dict with inc_vat, ex_vat, host_earnings, dao_earnings or None."""
    try:
        inc_vat      = float(quote_total_inc_vat)
        ex_vat       = inc_vat / (1 + VAT_RATE)
        host_earn    = ex_vat * HOST_SHARE
        dao_earn     = ex_vat * (1 - HOST_SHARE)
        return {
            "inc_vat":    inc_vat,
            "ex_vat":     ex_vat,
            "host_earn":  host_earn,
            "dao_earn":   dao_earn,
        }
    except (TypeError, ValueError):
        return None


# ── Message builder ───────────────────────────────────────────────────────────

def _build_message(
    client_name:  str,
    event_type:   str,
    event_date:   str,
    start_time:   str,
    end_time:     str,
    guest_count,
    rooms,
    order_number: str,
    cal_link:     str = "",
    airtable_id:  str = "",
    breakdown:    dict = None,
    host_claimed: str = "",
) -> str:
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
    ]

    if cal_link:
        lines.append(f"<b>Calendar:</b> <a href=\"{cal_link}\">View event ↗</a>")
    if airtable_id:
        lines.append(f"<b>Airtable:</b> <a href=\"https://airtable.com/{airtable_id}\">Open record ↗</a>")

    # Price breakdown
    if breakdown:
        lines += [
            "",
            "💰 <b>Revenue</b>",
            f"  Inc VAT:          {_fmt_eur(breakdown['inc_vat'])}",
            f"  Ex VAT:           {_fmt_eur(breakdown['ex_vat'])}",
            f"  Host (70%):       <b>{_fmt_eur(breakdown['host_earn'])}</b>",
            f"  DAO (30%):        {_fmt_eur(breakdown['dao_earn'])}",
        ]

    # Host line
    lines.append("")
    if host_claimed:
        lines.append(f"✅ <b>{host_claimed}</b> is hosting")
    else:
        lines.append("👤 <b>Who's hosting?</b>")

    lines.append(f"\n<i>Order #{order_number}</i>")
    return "\n".join(lines)


def _host_keyboard(record_id: str) -> dict:
    """Inline keyboard with one button per host."""
    hosts = ["Greg", "Dorian", "Bart"]
    return {
        "inline_keyboard": [[
            {"text": f"{name} 🙋", "callback_data": f"h:{name}:{record_id}"}
            for name in hosts
        ]]
    }


# ── Public API ────────────────────────────────────────────────────────────────

def notify_booking_confirmed(
    client_name:          str,
    event_type:           str,
    event_date:           str,
    start_time:           str,
    end_time:             str,
    guest_count,
    rooms,
    deposit_amount:       str,
    order_number:         str,
    airtable_id:          str = "",
    cal_link:             str = "",
    quote_total_inc_vat        = None,
) -> None:
    """Send the booking notification + host selection buttons to the group."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Not configured — skipping booking notification")
        return

    breakdown = _price_breakdown(quote_total_inc_vat)

    text = _build_message(
        client_name  = client_name,
        event_type   = event_type,
        event_date   = event_date,
        start_time   = start_time,
        end_time     = end_time,
        guest_count  = guest_count,
        rooms        = rooms,
        order_number = order_number,
        cal_link     = cal_link,
        airtable_id  = airtable_id,
        breakdown    = breakdown,
    )

    keyboard = _host_keyboard(airtable_id) if airtable_id else None

    kwargs = dict(
        chat_id    = TELEGRAM_CHAT_ID,
        text       = text,
        parse_mode = "HTML",
        disable_web_page_preview = True,
    )
    if keyboard:
        kwargs["reply_markup"] = keyboard

    result = _post("sendMessage", **kwargs)
    if result.get("ok"):
        print(f"[Telegram] Booking notification sent (order #{order_number})")
    else:
        print(f"[Telegram] Send failed: {result.get('description', result)}")


def handle_callback(update: dict) -> None:
    """
    Process an inline keyboard button press from Telegram.
    Called by the /telegram/webhook Flask route.
    Expected callback_data format: "h:{HostName}:{airtable_record_id}"
    """
    cq = update.get("callback_query", {})
    if not cq:
        return

    callback_id   = cq.get("id", "")
    data          = cq.get("data", "")
    from_user     = cq.get("from", {}).get("first_name", "Someone")
    message       = cq.get("message", {})
    chat_id       = message.get("chat", {}).get("id", "")
    message_id    = message.get("message_id", "")

    # Only handle host-claim callbacks
    if not data.startswith("h:"):
        _post("answerCallbackQuery", callback_query_id=callback_id)
        return

    parts = data.split(":", 2)   # ["h", "Greg", "recXXX"]
    if len(parts) < 3:
        _post("answerCallbackQuery", callback_query_id=callback_id)
        return

    _, host_name, record_id = parts

    # Write host to Airtable
    try:
        from airtable_client import update_inquiry
        update_inquiry(record_id, {"Host": host_name})
        print(f"[Telegram] Host set to {host_name} for record {record_id}")
    except Exception as e:
        print(f"[Telegram] Airtable host update failed: {e}")

    # Rebuild the original message text with the claimed host, without buttons
    orig_text = message.get("text", "")
    # Strip the "Who's hosting?" line and replace with confirmed host
    new_text = orig_text
    if "Who's hosting?" in new_text:
        new_text = new_text.replace("👤 Who's hosting?", f"✅ {host_name} is hosting")
    elif "is hosting" not in new_text:
        new_text = new_text + f"\n\n✅ {host_name} is hosting"

    # Edit the message — remove keyboard, update text
    _post(
        "editMessageText",
        chat_id      = chat_id,
        message_id   = message_id,
        text         = new_text,
        parse_mode   = "HTML",
        disable_web_page_preview = True,
        reply_markup = {"inline_keyboard": []},   # removes buttons
    )

    # Acknowledge the button press — shows a brief toast to the tapper
    _post(
        "answerCallbackQuery",
        callback_query_id = callback_id,
        text              = f"✅ Logged — {host_name} is hosting",
        show_alert        = False,
    )


# ── Setup helpers (run once) ──────────────────────────────────────────────────

def get_chat_id() -> None:
    """
    Run once to find the group chat ID after adding the bot and sending a message.
    Usage: python3 -c "from telegram_notify import get_chat_id; get_chat_id()"
    """
    result = _post("getUpdates")
    updates = result.get("result", [])
    if not updates:
        print("No updates. Send a message in your group first, then retry.")
        return
    seen = set()
    for u in updates[-10:]:
        chat = (u.get("message") or u.get("my_chat_member", {}).get("chat", {}))
        if isinstance(chat, dict):
            cid = chat.get("id")
            if cid and cid not in seen:
                seen.add(cid)
                print(f"  Chat ID: {cid}  |  Type: {chat.get('type')}  |  Name: {chat.get('title', chat.get('first_name', ''))}")


def register_webhook() -> None:
    """
    Register the server's /telegram/webhook URL with Telegram.
    Run once after deployment: python3 -c "from telegram_notify import register_webhook; register_webhook()"
    """
    webhook_url = f"{BASE_URL}/telegram/webhook"
    result = _post("setWebhook", url=webhook_url, allowed_updates=["callback_query"])
    if result.get("ok"):
        print(f"[Telegram] Webhook registered → {webhook_url}")
    else:
        print(f"[Telegram] Webhook registration failed: {result}")


def send_message(text: str, chat_id: str = None) -> dict:
    """Send a plain text message (utility / testing)."""
    cid = chat_id or TELEGRAM_CHAT_ID
    if not cid:
        return {}
    return _post("sendMessage", chat_id=cid, text=text, parse_mode="HTML",
                 disable_web_page_preview=True)
