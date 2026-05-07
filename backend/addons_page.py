"""
addons_page.py
--------------
HMAC-secured add-ons modification page for confirmed bookings.
Linked from the confirmation email so clients can add or adjust
add-ons after booking. Updates Airtable Balance Due on submit.

Routes registered in app.py:
  GET  /addons?record=xxx&token=xxx   — show the form
  POST /addons/submit                  — process and update Airtable
"""

import os
import hmac
import hashlib
import json
from flask import Blueprint, request, abort, Response
from datetime import datetime as _dt

ADDONS_SECRET = os.getenv("ARRIVAL_SECRET", "sauvage-arrival-secret-change-me")
BASE_URL      = os.getenv("BASE_URL", "https://sauvage.amsterdam")

addons_bp = Blueprint("addons", __name__)

# ── Add-on catalogue ──────────────────────────────────────────────────────────
# (id, label, price_label, unit, unit_price, note, airtable_option)
# airtable_option = exact Multiple Select value, or None to write to Notes instead
ADDONS = [
    ("dishware",        "Dishware & Cutlery & Glass (25 pax)",          "€25",      "flat",   25,   "",                                   "Dishware & Cutlery"),
    ("glassware",       "Stem (wine) Glassware (25 pax)",               "€25",      "flat",   25,   "",                                   "Stem Glassware"),
    ("staff",           "Staff Support",                                 "€35/hr pp","hr_pp",  35,   "Per person, per hour",               "Staff Support"),
    ("bar",             "Bar / Barista Service",                         "€50/hr",   "hr",     50,   "Drinks charged on site separately",  "Sommelier/Barista Service"),
    ("extended_hours",  "Extended Hours (after midnight)",               "€50/hr",   "hr",     50,   "",                                   None),
    ("cleanup",         "Event Cleanup",                                 "€60",      "flat",   60,   "",                                   "Event Cleanup"),
    ("snacks_light",    "Light Snacks — seasonal bites (Fento)",        "€5/pp",    "pp",     5,    "Must order ≥7 days before event",    "Light Snacks Fento"),
    ("snacks",          "Snacks — borrel-style spread (Fento)",         "€10/pp",   "pp",     10,   "Must order ≥7 days before event",    "Snacks Fento"),
    ("projector",       "Projector / Display Screen",                   "€25",      "flat",   25,   "",                                   "Projector/Display Screen"),
]


def _token(record_id: str) -> str:
    return hmac.new(
        ADDONS_SECRET.encode(), record_id.encode(), hashlib.sha256
    ).hexdigest()[:32]


def _verify(record_id: str, token: str) -> bool:
    return hmac.compare_digest(_token(record_id), token)


def _fmt_date(raw: str) -> str:
    try:
        return _dt.strptime(str(raw).strip()[:10], "%Y-%m-%d").strftime("%A %-d %B %Y")
    except Exception:
        return str(raw)


def _fmt_rooms(rooms) -> str:
    if isinstance(rooms, list):
        return ", ".join(str(r) for r in rooms)
    return str(rooms or "TBC")


def _get_booking(record_id: str) -> dict:
    try:
        from airtable_client import get_inquiry
        rec = get_inquiry(record_id)
        if rec:
            return rec.get("fields", {})
    except Exception as e:
        print(f"[Addons] Airtable fetch failed: {e}")
    return {}


@addons_bp.route("/addons")
def addons_form():
    record_id = request.args.get("record", "")
    token     = request.args.get("token", "")

    if not record_id or not _verify(record_id, token):
        abort(403)

    fields      = _get_booking(record_id)
    client_name = fields.get("Name", "")
    event_type  = fields.get("Event Type", "Event")
    event_date  = _fmt_date(fields.get("Requested Date", ""))
    start_time  = fields.get("Start Time", "")
    end_time    = fields.get("End Time", "")
    rooms_str   = _fmt_rooms(fields.get("Rooms", []))
    guest_count = fields.get("Guest Count", "")
    balance_due = fields.get("Balance Due", 0) or 0
    total_incl  = fields.get("Total Incl VAT", 0) or 0

    # Parse Time Slot into start/end if dedicated fields not present
    time_slot = fields.get("Time Slot", "")
    if not start_time and not end_time and time_slot and "-" in time_slot:
        parts = time_slot.split("-", 1)
        start_time = parts[0].strip()
        end_time   = parts[1].strip()
    time_str = f"{start_time} – {end_time}" if start_time and end_time else time_slot or "TBC"

    # Build add-on rows HTML
    addon_rows = ""
    for aid, label, price_label, unit, unit_price, note, _at_option in ADDONS:
        note_html = f'<span class="note">{note}</span>' if note else ""
        if unit == "flat":
            addon_rows += f"""
        <div class="addon-row" data-id="{aid}" data-unit="flat" data-price="{unit_price}">
          <label class="addon-label">
            <input type="checkbox" name="addon_{aid}" value="1" onchange="recalc()">
            <span class="addon-name">{label}</span>
            <span class="addon-price">{price_label}</span>
          </label>
          {note_html}
        </div>"""
        elif unit == "pp":
            addon_rows += f"""
        <div class="addon-row" data-id="{aid}" data-unit="pp" data-price="{unit_price}">
          <label class="addon-label">
            <input type="checkbox" name="addon_{aid}_check" value="1" onchange="recalc()">
            <span class="addon-name">{label}</span>
            <span class="addon-price">{price_label}</span>
          </label>
          <div class="qty-row addon-qty" style="display:none;">
            <label>Guests: <input type="number" name="addon_{aid}_qty" min="1" max="30"
                   value="{guest_count or 1}" class="qty-input" onchange="recalc()"></label>
          </div>
          {note_html}
        </div>"""
        elif unit == "hr":
            addon_rows += f"""
        <div class="addon-row" data-id="{aid}" data-unit="hr" data-price="{unit_price}">
          <label class="addon-label">
            <input type="checkbox" name="addon_{aid}_check" value="1" onchange="recalc()">
            <span class="addon-name">{label}</span>
            <span class="addon-price">{price_label}</span>
          </label>
          <div class="qty-row addon-qty" style="display:none;">
            <label>Hours: <input type="number" name="addon_{aid}_qty" min="1" max="12"
                   value="1" class="qty-input" onchange="recalc()"></label>
          </div>
          {note_html}
        </div>"""
        elif unit == "hr_pp":
            addon_rows += f"""
        <div class="addon-row" data-id="{aid}" data-unit="hr_pp" data-price="{unit_price}">
          <label class="addon-label">
            <input type="checkbox" name="addon_{aid}_check" value="1" onchange="recalc()">
            <span class="addon-name">{label}</span>
            <span class="addon-price">{price_label}</span>
          </label>
          <div class="qty-row addon-qty" style="display:none;">
            <label>Hours: <input type="number" name="addon_{aid}_hrs" min="1" max="12"
                   value="1" class="qty-input" onchange="recalc()"></label>
            <label style="margin-left:12px;">People: <input type="number" name="addon_{aid}_ppl" min="1" max="10"
                   value="1" class="qty-input" onchange="recalc()"></label>
          </div>
          {note_html}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Add-ons — Sauvage Space</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 40px 20px 80px;
      background: #f5f3ef;
      font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
      color: #1a1a1a;
    }}
    .wrap {{ max-width: 560px; margin: 0 auto; }}
    .logo-row {{
      font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase;
      color: #aaa; margin-bottom: 32px;
    }}
    h1 {{
      font-family: Georgia, serif; font-size: 26px; font-weight: 300;
      color: #1a1a18; margin: 0 0 4px;
    }}
    .subtitle {{ font-size: 13px; color: #999; margin: 0 0 32px; }}
    .booking-card {{
      background: #fff; border-radius: 4px; padding: 24px 28px;
      margin-bottom: 28px; border: 1px solid #e8e4de;
    }}
    .booking-card p {{ margin: 0 0 4px; }}
    .booking-card .label {{
      font-size: 10px; letter-spacing: 0.15em; text-transform: uppercase;
      color: #aaa; margin-bottom: 2px;
    }}
    .booking-card .value {{ font-size: 14px; font-weight: 500; color: #1a1a18; }}
    .booking-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .section-title {{
      font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase;
      color: #b8860b; margin: 0 0 16px; font-weight: 700;
    }}
    .addon-row {{
      background: #fff; border: 1px solid #e8e4de; border-radius: 3px;
      padding: 14px 16px; margin-bottom: 8px;
    }}
    .addon-label {{
      display: flex; align-items: center; cursor: pointer; gap: 10px;
    }}
    .addon-label input[type=checkbox] {{ width: 16px; height: 16px; flex-shrink: 0; accent-color: #b8860b; }}
    .addon-name {{ flex: 1; font-size: 14px; color: #1a1a18; }}
    .addon-price {{
      font-size: 13px; font-weight: 600; color: #b8860b; white-space: nowrap;
    }}
    .note {{ display: block; font-size: 11px; color: #aaa; margin-top: 4px; padding-left: 26px; }}
    .addon-qty {{ margin-top: 10px; padding-left: 26px; }}
    .qty-input {{
      width: 60px; padding: 4px 8px; border: 1px solid #ddd; border-radius: 3px;
      font-size: 14px; text-align: center;
    }}
    .total-bar {{
      background: #1a1a18; color: #fff; border-radius: 4px;
      padding: 20px 24px; margin: 24px 0; display: flex;
      justify-content: space-between; align-items: center;
    }}
    .total-bar .label {{ font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase; color: #b8860b; }}
    .total-bar .amount {{ font-family: Georgia, serif; font-size: 28px; font-weight: 300; }}
    .total-bar .breakdown {{ font-size: 12px; color: rgba(255,255,255,0.45); margin-top: 2px; }}
    .btn {{
      display: block; width: 100%; background: #b8860b; color: #fff;
      border: none; border-radius: 3px; padding: 16px;
      font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
      font-size: 10px; font-weight: 700; letter-spacing: 0.22em;
      text-transform: uppercase; cursor: pointer;
    }}
    .btn:hover {{ background: #a07808; }}
    .footer {{ margin-top: 32px; font-size: 12px; color: #aaa; text-align: center; }}
    .footer a {{ color: #888; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="logo-row">Sauvage Space · Amsterdam</div>
    <h1>Add-ons</h1>
    <p class="subtitle">Modify your add-ons for this booking. Any additions will be added to your balance.</p>

    <div class="booking-card">
      <p class="label">Event</p>
      <p class="value" style="margin-bottom:16px;">{event_type}</p>
      <div class="booking-grid">
        <div><p class="label">Date</p><p class="value">{event_date}</p></div>
        <div><p class="label">Time</p><p class="value">{time_str}</p></div>
        <div><p class="label">Space</p><p class="value">{rooms_str}</p></div>
        <div><p class="label">Guests</p><p class="value">{guest_count}</p></div>
      </div>
    </div>

    <p class="section-title">Available add-ons</p>

    <form method="POST" action="/addons/submit" id="addons-form">
      <input type="hidden" name="record_id" value="{record_id}">
      <input type="hidden" name="token" value="{token}">
      <input type="hidden" name="addons_json" id="addons_json" value="">

      {addon_rows}

      <div class="total-bar">
        <div>
          <div class="label">Add-ons total</div>
          <div class="amount" id="addons-total">€0</div>
          <div class="breakdown" id="addons-breakdown">No add-ons selected</div>
        </div>
      </div>

      <button type="submit" class="btn" onclick="return prepareSubmit()">
        Confirm add-ons &rarr;
      </button>
    </form>

    <div class="footer">
      Questions? <a href="https://wa.me/31634742988">WhatsApp Greg</a> &nbsp;·&nbsp;
      <a href="https://sauvage.amsterdam">sauvage.amsterdam</a>
    </div>
  </div>

  <script>
    function recalc() {{
      var rows = document.querySelectorAll('.addon-row');
      var total = 0;
      var lines = [];

      rows.forEach(function(row) {{
        var unit  = row.dataset.unit;
        var price = parseFloat(row.dataset.price);
        var id    = row.dataset.id;
        var cb    = row.querySelector('input[type=checkbox]');
        var qty   = row.querySelector('.addon-qty');

        if (!cb || !cb.checked) {{
          if (qty) qty.style.display = 'none';
          return;
        }}
        if (qty) qty.style.display = 'block';

        var label = row.querySelector('.addon-name').textContent.trim();
        var amt = 0;

        if (unit === 'flat') {{
          amt = price;
          lines.push(label + ': €' + amt.toFixed(0));
        }} else if (unit === 'pp') {{
          var n = parseInt(row.querySelector('.qty-input').value) || 1;
          amt = price * n;
          lines.push(label + ' × ' + n + ': €' + amt.toFixed(0));
        }} else if (unit === 'hr') {{
          var h = parseInt(row.querySelector('.qty-input').value) || 1;
          amt = price * h;
          lines.push(label + ' × ' + h + 'hr: €' + amt.toFixed(0));
        }} else if (unit === 'hr_pp') {{
          var hrs = parseInt(row.querySelector('[name$="_hrs"]').value) || 1;
          var ppl = parseInt(row.querySelector('[name$="_ppl"]').value) || 1;
          amt = price * hrs * ppl;
          lines.push(label + ' ' + hrs + 'hr × ' + ppl + ' staff: €' + amt.toFixed(0));
        }}
        total += amt;
      }});

      document.getElementById('addons-total').textContent = '€' + total.toFixed(2);
      document.getElementById('addons-breakdown').textContent =
        lines.length ? lines.join(' · ') : 'No add-ons selected';
    }}

    function prepareSubmit() {{
      var rows = document.querySelectorAll('.addon-row');
      var selected = [];
      var total = 0;

      rows.forEach(function(row) {{
        var unit  = row.dataset.unit;
        var price = parseFloat(row.dataset.price);
        var id    = row.dataset.id;
        var cb    = row.querySelector('input[type=checkbox]');
        if (!cb || !cb.checked) return;

        var label = row.querySelector('.addon-name').textContent.trim();
        var qty = 1, hrs = 1, ppl = 1, amt = 0;

        if (unit === 'flat') {{
          amt = price;
          selected.push({{id:id, label:label, unit:unit, qty:1, amt:amt}});
        }} else if (unit === 'pp') {{
          qty = parseInt(row.querySelector('.qty-input').value) || 1;
          amt = price * qty;
          selected.push({{id:id, label:label, unit:unit, qty:qty, amt:amt}});
        }} else if (unit === 'hr') {{
          qty = parseInt(row.querySelector('.qty-input').value) || 1;
          amt = price * qty;
          selected.push({{id:id, label:label, unit:unit, qty:qty, amt:amt}});
        }} else if (unit === 'hr_pp') {{
          hrs = parseInt(row.querySelector('[name$="_hrs"]').value) || 1;
          ppl = parseInt(row.querySelector('[name$="_ppl"]').value) || 1;
          amt = price * hrs * ppl;
          selected.push({{id:id, label:label, unit:unit, hrs:hrs, ppl:ppl, amt:amt}});
        }}
        total += amt;
      }});

      document.getElementById('addons_json').value = JSON.stringify({{
        selected: selected,
        total_addons: parseFloat(total.toFixed(2))
      }});
      return true;
    }}
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")


@addons_bp.route("/addons/submit", methods=["POST"])
def addons_submit():
    record_id = request.form.get("record_id", "")
    token     = request.form.get("token", "")
    raw       = request.form.get("addons_json", "{}")

    if not record_id or not _verify(record_id, token):
        abort(403)

    try:
        data         = json.loads(raw)
        selected     = data.get("selected", [])
        total_addons = float(data.get("total_addons", 0))
    except Exception:
        abort(400)

    # Build summary lines and map to Airtable Multiple Select options
    _at_map = {a[0]: a[6] for a in ADDONS}   # id → airtable_option (or None)
    lines        = []   # human-readable summary
    at_options   = []   # Airtable Multiple Select values
    notes_extras = []   # items with no Airtable option (e.g. Extended Hours)

    for item in selected:
        aid   = item.get("id", "")
        unit  = item.get("unit")
        label = item.get("label", "")
        amt   = item.get("amt", 0)

        if unit == "flat":
            lines.append(f"{label}: €{amt:.0f}")
        elif unit == "pp":
            lines.append(f"{label} × {item.get('qty',1)}: €{amt:.0f}")
        elif unit == "hr":
            lines.append(f"{label} × {item.get('qty',1)}hr: €{amt:.0f}")
        elif unit == "hr_pp":
            lines.append(f"{label} {item.get('hrs',1)}hr × {item.get('ppl',1)} staff: €{amt:.0f}")

        at_opt = _at_map.get(aid)
        if at_opt:
            at_options.append(at_opt)
        else:
            notes_extras.append(lines[-1])   # store detail in Notes instead

    addons_summary = " | ".join(lines) if lines else "None"

    # Update Airtable: Balance Due + Add-ons (array) + Notes for unmapped items
    try:
        from airtable_client import get_inquiry, update_inquiry
        fields      = (get_inquiry(record_id) or {}).get("fields", {})
        current_bal = float(fields.get("Balance Due", 0) or 0)
        new_balance = round(current_bal + total_addons, 2)

        update_fields = {"Balance Due": new_balance}

        if at_options:
            existing = fields.get("Add-ons", []) or []
            if isinstance(existing, str):
                existing = [existing] if existing else []
            merged = list(dict.fromkeys(existing + at_options))   # dedupe, preserve order
            update_fields["Add-ons"] = merged

        if notes_extras:
            existing_notes = fields.get("Notes", "") or ""
            extras_str = "; ".join(notes_extras)
            update_fields["Notes"] = (existing_notes + "\n" if existing_notes else "") + f"Add-ons: {extras_str}"

        update_inquiry(record_id, update_fields)
        print(f"[Addons] {record_id} — +€{total_addons:.2f} → balance now €{new_balance:.2f}")
    except Exception as e:
        print(f"[Addons] Airtable update failed: {e}")

    # Telegram alert
    if lines:
        try:
            from telegram_notify import send_message
            fields = (get_inquiry(record_id) or {}).get("fields", {})
            name   = fields.get("Name", "Client")
            ev     = fields.get("Event Type", "Event")
            dt     = fields.get("Requested Date", "")
            send_message(
                f"➕ <b>Add-ons updated</b>\n"
                f"👤 {name} · {ev} · {dt}\n"
                f"{addons_summary}\n"
                f"<b>+€{total_addons:.2f}</b> added to balance"
            )
        except Exception as e:
            print(f"[Addons] Telegram alert failed: {e}")

    return Response(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Add-ons confirmed</title></head>
<body style="margin:0;padding:60px 24px;background:#f5f3ef;
             font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;text-align:center;">
  <p style="font-size:11px;letter-spacing:0.18em;text-transform:uppercase;
             color:#b8860b;margin:0 0 16px;">Sauvage Amsterdam</p>
  <h1 style="font-size:26px;font-weight:300;font-family:Georgia,serif;
              color:#1a1a18;margin:0 0 16px;">Add-ons confirmed.</h1>
  <p style="font-size:14px;color:#666;max-width:360px;margin:0 auto 24px;line-height:1.75;">
    {"Your selections have been added and your balance has been updated. You'll receive a payment link shortly." if lines else "No changes made."}
  </p>
  {"<p style='font-size:13px;color:#aaa;max-width:400px;margin:0 auto;line-height:1.7;'>" + addons_summary + "</p>" if lines else ""}
</body></html>""", mimetype="text/html")
