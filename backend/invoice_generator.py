"""
invoice_generator.py
--------------------
Generates PDF invoices / quote PDFs for Sauvage bookings (RNR-YYYY-NNN format).
Issued by Roots & Remedies Stichting on behalf of Sauvage DAO.

Public API:
    compute_line_items(state)  → list of line-item dicts with full pricing breakdown
    build_quote_pdf(state)     → bytes  (proforma / "Export as PDF" button)
    build_invoice(state, ...)  → (invoice_number, bytes)  (confirmed booking)
    save_invoice(num, bytes)   → path
    invoice_url(num)           → HMAC-gated URL string
    verify_invoice_token(num, token) → bool
"""

import io
import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas as rl_canvas

# ── Business constants ─────────────────────────────────────────────────────────
COMPANY_NAME   = "Roots & Remedies Stichting"
COMPANY_ADDR   = "Potgieterstraat 47 H · 1053XS Amsterdam · Netherlands"
COMPANY_KVK    = "KvK: 76681629"
COMPANY_BTW    = "BTW: NL860744875B01"
COMPANY_IBAN   = "NL42 TRIO 0788 8783 60"
COMPANY_BIC    = "TRIONL2U"
COMPANY_EMAIL  = "hello@rootsandremedies.earth"
COMPANY_BEHALF = "Issued on behalf of Sauvage DAO"

VAT_RATE   = 0.21
DUE_DAYS   = 7

_DB_PATH    = os.path.join(os.path.dirname(__file__), "sessions.db")
_INV_DIR    = os.path.join(os.path.dirname(__file__), "invoices")
_LOGO_PATH  = os.path.join(os.path.dirname(__file__), "assets", "sauvage-logo.png")

# ── Colour palette ─────────────────────────────────────────────────────────────
C_BLACK = colors.HexColor("#1a1a1a")
C_GOLD  = colors.HexColor("#b8860b")
C_GRAY  = colors.HexColor("#888888")
C_LGRAY = colors.HexColor("#cccccc")
C_BG    = colors.HexColor("#f5f3ef")
C_NOTE  = colors.HexColor("#faf8f0")
C_WHITE = colors.white

# ── Pricing tables (all incl 21% VAT) ─────────────────────────────────────────
_ROOM_ALIASES = {
    "gallery":                "gallery",
    "upstairs":               "gallery",
    "upstairs (gallery)":     "gallery",
    "gallery (upstairs)":     "gallery",
    "upstairs — gallery":     "gallery",
    "upstairs - gallery":     "gallery",
    "gallery — upstairs":     "gallery",
    "entrance":               "entrance",
    "entrance room":          "entrance",
    # Kitchen — single tier (canonical v3)
    "kitchen":                "kitchen",
    "kitchen_full":           "kitchen",   # legacy alias
    "kitchen (full stove)":   "kitchen",
    "kitchen full stove":     "kitchen",
    "kitchen full":           "kitchen",
    "kitchen_basic":          "kitchen",   # legacy alias → now same rate
    "kitchen (basic)":        "kitchen",
    "kitchen basic":          "kitchen",
    "kitchen (no stove)":     "kitchen",
    "kitchen no stove":       "kitchen",
    # Cave
    "cave":                   "cave",
    "wine cave":              "cave",
}

_ROOM_LABELS = {
    "gallery":  "Upstairs (Gallery)",
    "entrance": "Entrance Room",
    "kitchen":  "Kitchen",
    "cave":     "Cave",
}

_ROOM_RATES = {
    # key: (half_day, full_day)   — all incl VAT
    # canonical v3: half-day is the only bot-quoted slot
    # full-day rates defined but not bot-quoted — kept for reference
    "gallery":  (135, 140),
    "entrance": (190, 250),
    "kitchen":  (350, 500),
    "cave":     (100, 175),   # host fee added separately — see _CAVE_HOST_FEE
}

_CAVE_HOST_FEE = 35   # €35/hr incl VAT — added as separate line item when cave booked

_BUNDLE_DISCOUNTS = {1: 0.0, 2: 0.20, 3: 0.40, 4: 0.50}

# Full-day closure fees kept for reference but not used in bot quoting
_CLOSURE_FEES = {
    "entrance": 200,   # full-day only, incl VAT
    "kitchen":  100,   # full-day only, incl VAT
}

# Add-on prices incl VAT; "pp" = per person, "hr" = per hour, "flat" = fixed
# canonical v3 rates
_ADDON_RATES = {
    "light snacks fento":              (5,  "pp"),
    "snacks fento":                    (10, "pp"),
    "snacks light fento":              (5,  "pp"),
    "event cleanup":                   (60, "flat"),
    "stemless glassware":              (25, "flat"),
    "stem glassware":                  (25, "flat"),   # same price as stemless (v3)
    "dishware & cutlery":              (25, "flat"),
    "dishware and cutlery":            (25, "flat"),
    "staff support":                   (35, "hr"),
    "bar/barista service":             (40, "hr"),     # v3: €40/hr (was €50)
    "bar barista service":             (40, "hr"),
    "sommelier/barista service":       (40, "hr"),     # legacy alias
    "sommelier barista service":       (40, "hr"),
    "decor/styling package":           (50, "flat"),   # new in v3, from €50
    "decor styling package":           (50, "flat"),
    "projector/display screen":        (25, "flat"),
    "projector display screen":        (25, "flat"),
    "extended hours (after midnight)": (50, "hr"),
    "extended hours after midnight":   (50, "hr"),
    "cave host fee":                   (35, "hr"),     # cave host presence
}

def _norm_room(r: str) -> str:
    return _ROOM_ALIASES.get(r.strip().lower(), "")

def _norm_addon(a: str) -> str:
    """Normalise an add-on name to the key used in _ADDON_RATES."""
    s = re.sub(r"[^a-z0-9 /]", " ", a.strip().lower())
    s = re.sub(r"\s+", " ", s).strip()
    if s in _ADDON_RATES:
        return s
    for key in _ADDON_RATES:
        if key in s or s in key:
            return key
    # keyword fallback
    if "light" in s and ("snack" in s or "fento" in s):
        return "light snacks fento"
    if "fento" in s or "snack" in s:
        return "snacks fento"
    if "cleanup" in s or "clean" in s:
        return "event cleanup"
    if "stemless" in s or ("glass" in s and "stem" not in s):
        return "stemless glassware"
    if "stem" in s and "glass" in s:
        return "stem glassware"
    if "dish" in s or "cutlery" in s:
        return "dishware & cutlery"
    if "staff" in s:
        return "staff support"
    if "bar" in s or "sommelier" in s or "barista" in s:
        return "bar/barista service"
    if "projector" in s or "screen" in s or "display" in s:
        return "projector/display screen"
    if "extended" in s or "midnight" in s:
        return "extended hours (after midnight)"
    return ""


# ── Pricing engine ─────────────────────────────────────────────────────────────

def compute_line_items(state: dict) -> list[dict]:
    """
    Build a fully itemised list of line items from session state.

    Each item is a dict:
        description  str
        qty          float
        unit_str     str   e.g. "hr", "pax", "flat"
        unit_incl    float  unit price incl VAT
        total_incl   float  line total incl VAT
        total_ex     float  line total ex VAT
        vat_amt      float  VAT amount
        vat_rate     float  e.g. 0.21
        is_discount  bool
        is_deposit   bool
    """
    rooms_raw  = state.get("rooms") or []
    if isinstance(rooms_raw, str):
        rooms_raw = [rooms_raw]
    rooms = [_norm_room(r) for r in rooms_raw if _norm_room(r)]
    rooms = list(dict.fromkeys(rooms))   # deduplicate, preserve order

    duration   = str(state.get("duration") or "Half-Day").lower()
    hours      = float(state.get("hours") or 0)
    # Derive hours from actual start/end times when available
    if state.get("start_time") and state.get("end_time"):
        try:
            _st = datetime.strptime(str(state["start_time"]).strip(), "%H:%M")
            _et = datetime.strptime(str(state["end_time"]).strip(),   "%H:%M")
            _computed = (_et - _st).seconds / 3600
            if _computed > 0:
                hours = round(_computed * 2) / 2
        except ValueError:
            pass
    dates_val  = state.get("dates")
    guest      = int(state.get("guest_count") or 0)
    addons_raw = state.get("addons") or []
    if isinstance(addons_raw, str):
        addons_raw = [addons_raw]

    # Number of slots (days) for multi-day bookings
    if isinstance(dates_val, list) and len(dates_val) >= 2:
        try:
            d0 = datetime.strptime(str(dates_val[0]).strip(),  "%Y-%m-%d")
            d1 = datetime.strptime(str(dates_val[-1]).strip(), "%Y-%m-%d")
            num_days = (d1 - d0).days + 1
        except ValueError:
            num_days = 1
    else:
        num_days = 1

    is_full_day = "full" in duration
    # Default is half-day (canonical v3 — bot only quotes half-day)
    # hours used for cave host fee and add-on per-hour items
    if hours == 0:
        hours = 7.0   # standard half-day = 7 hrs (16:00–23:00)

    items = []

    def _line(desc, qty, unit_str, unit_incl, vat_rate=VAT_RATE,
              is_discount=False, is_deposit=False):
        total_incl = round(qty * unit_incl, 2)
        total_ex   = round(total_incl / (1 + vat_rate), 2)
        vat_amt    = round(total_incl - total_ex, 2)
        items.append({
            "description": desc,
            "qty":         qty,
            "unit_str":    unit_str,
            "unit_incl":   unit_incl,
            "total_incl":  total_incl,
            "total_ex":    total_ex,
            "vat_amt":     vat_amt,
            "vat_rate":    vat_rate,
            "is_discount": is_discount,
            "is_deposit":  is_deposit,
        })

    # ── Room line items ────────────────────────────────────────────────────────
    room_pre_discount = 0.0
    has_cave = "cave" in rooms
    for r in rooms:
        label = _ROOM_LABELS.get(r, r.title())
        rates = _ROOM_RATES.get(r, (0, 0))
        half_rate, full_rate = rates

        if is_full_day:
            unit  = full_rate
            qty   = num_days
            u_str = "day"
            desc  = f"Space rental: {label} (full day)"
        else:  # half-day (canonical default)
            unit  = half_rate
            qty   = num_days
            u_str = "slot"
            desc  = f"Space rental: {label} (half day)"

        room_pre_discount += unit * qty
        _line(desc, qty, u_str, unit)

    # Bundle discount
    n_rooms = len(rooms)
    discount_pct = _BUNDLE_DISCOUNTS.get(n_rooms, 0.0)
    if discount_pct > 0 and room_pre_discount > 0:
        discount_amt = round(room_pre_discount * discount_pct, 2)
        _line(
            f"Bundle discount ({n_rooms} rooms, {int(discount_pct*100)}%)",
            1, "", -discount_amt,
            is_discount=True,
        )

    # Cave host fee — separate line item, scales with booked hours
    if has_cave:
        cave_hours = hours * num_days
        _line(
            f"Cave host fee × {cave_hours:.0f} hrs",
            cave_hours, "hr", _CAVE_HOST_FEE,
        )

    # Full-day closure premiums (reference only — not bot-quoted)
    if is_full_day:
        for r in rooms:
            if r in _CLOSURE_FEES:
                fee = _CLOSURE_FEES[r] * num_days
                _line(
                    f"{_ROOM_LABELS.get(r, r.title())} closure fee"
                    + (f" × {num_days} days" if num_days > 1 else ""),
                    1, "flat", fee,
                )

    # ── Add-on line items ──────────────────────────────────────────────────────
    for raw in addons_raw:
        key = _norm_addon(raw)
        if not key or key not in _ADDON_RATES:
            continue
        price, unit_type = _ADDON_RATES[key]
        label = " ".join(w.capitalize() for w in key.split())

        if unit_type == "pp":
            qty_a  = guest or 1
            u_str  = "pax"
            desc   = f"{label} × {qty_a} guests"
        elif unit_type == "hr":
            qty_a  = hours or 1
            u_str  = "hr"
            desc   = f"{label} × {qty_a} hrs"
        else:
            qty_a  = 1
            u_str  = "flat"
            desc   = label
        _line(desc, qty_a, u_str, price)

    return items


def _sum_items(items: list[dict]) -> dict:
    total_ex  = round(sum(i["total_ex"]  for i in items if not i.get("is_deposit")), 2)
    total_vat = round(sum(i["vat_amt"]   for i in items if not i.get("is_deposit")), 2)
    total_inc = round(sum(i["total_incl"] for i in items if not i.get("is_deposit")), 2)
    deposit   = round(sum(i["total_incl"] for i in items if     i.get("is_deposit")), 2)
    return {
        "total_ex":  total_ex,
        "total_vat": total_vat,
        "total_inc": total_inc,
        "deposit":   deposit,
        "total_due": round(total_inc + deposit, 2),
    }


def compute_revenue_breakdown(state: dict) -> dict:
    """
    Split the event total into rental fees vs pass-through add-ons.

    70%/30% split applies to rental fees only (rooms + bundle discounts).
    Fento snacks, wines, and other add-ons are pass-throughs — not split.

    Returns:
      {
        "rental_inc_vat":  float,   # rooms (after bundle discount) inc VAT
        "rental_ex_vat":   float,   # rooms ex VAT  → apply 70/30 to this
        "host_earn":       float,   # 70% of rental_ex_vat
        "dao_earn":        float,   # 30% of rental_ex_vat
        "addons_inc_vat":  float,   # add-ons total inc VAT (pass-through)
        "addons_lines":    list,    # [{"description": str, "total_incl": float}, ...]
        "total_inc_vat":   float,
        "total_ex_vat":    float,
      }
    """
    HOST_SHARE = 0.70
    items = compute_line_items(state)

    rental_items = [i for i in items
                    if i["description"].startswith("Space rental")
                    or i.get("is_discount")
                    or "closure fee" in i["description"]]

    addon_items  = [i for i in items
                    if not i["description"].startswith("Space rental")
                    and not i.get("is_discount")
                    and "closure fee" not in i["description"]
                    and not i.get("is_deposit")]

    rental_inc = round(sum(i["total_incl"] for i in rental_items), 2)
    rental_ex  = round(sum(i["total_ex"]   for i in rental_items), 2)
    addons_inc = round(sum(i["total_incl"] for i in addon_items),  2)

    totals = _sum_items(items)

    return {
        "rental_inc_vat": rental_inc,
        "rental_ex_vat":  rental_ex,
        "host_earn":      round(rental_ex * HOST_SHARE, 2),
        "dao_earn":       round(rental_ex * (1 - HOST_SHARE), 2),
        "addons_inc_vat": addons_inc,
        "addons_lines":   [{"description": i["description"],
                            "total_incl":  i["total_incl"]} for i in addon_items],
        "total_inc_vat":  totals["total_inc"],
        "total_ex_vat":   totals["total_ex"],
    }


# ── Date / room helpers ────────────────────────────────────────────────────────

def _fmt_date_range(dates) -> str:
    if not dates:
        return ""
    if isinstance(dates, list) and len(dates) >= 2:
        try:
            d0 = datetime.strptime(str(dates[0]).strip(),  "%Y-%m-%d")
            d1 = datetime.strptime(str(dates[-1]).strip(), "%Y-%m-%d")
            if d0.month == d1.month:
                return f"{d0.day} to {d1.day} {d0.strftime('%B %Y')}"
            return f"{d0.strftime('%-d %b')} to {d1.strftime('%-d %b %Y')}"
        except ValueError:
            return f"{dates[0]} to {dates[-1]}"
    if isinstance(dates, list):
        val = dates[0]
    else:
        val = dates
    try:
        return datetime.strptime(str(val).strip(), "%Y-%m-%d").strftime("%-d %B %Y")
    except ValueError:
        return str(val)


def _fmt_rooms(rooms) -> str:
    if not rooms:
        return "Sauvage Space"
    if isinstance(rooms, list):
        return " + ".join(rooms)
    return str(rooms)


# ── Invoice counter ────────────────────────────────────────────────────────────

def next_invoice_number(year: Optional[int] = None) -> str:
    if year is None:
        year = datetime.now().year
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoice_counter
        (year INTEGER PRIMARY KEY, last_num INTEGER DEFAULT 0)
    """)
    row = conn.execute(
        "SELECT last_num FROM invoice_counter WHERE year = ?", (year,)
    ).fetchone()
    last    = row[0] if row else 0
    new_num = last + 1
    conn.execute(
        "INSERT OR REPLACE INTO invoice_counter (year, last_num) VALUES (?, ?)",
        (year, new_num),
    )
    conn.commit()
    conn.close()
    return f"RNR-{year}-{new_num:03d}"


# ── PDF renderer ───────────────────────────────────────────────────────────────

def _money(v: float) -> str:
    if v < 0:
        return f"-€ {abs(v):,.2f}".replace(",", "\u202f")
    return f"€ {v:,.2f}".replace(",", "\u202f")


def _render_pdf(
    state:          dict,
    line_items:     list[dict],
    totals:         dict,
    invoice_number: str = "",       # empty → "QUOTE / PRO-FORMA"
    issued_date:    Optional[datetime] = None,
    deposit_paid:   float = 0.0,
    record_id:      str = "",
) -> bytes:
    """Core PDF renderer — used by both build_quote_pdf and build_invoice."""

    if issued_date is None:
        issued_date = datetime.now()
    due_date = issued_date + timedelta(days=DUE_DAYS)

    is_quote   = not invoice_number
    doc_title  = "QUOTE" if is_quote else "INVOICE"
    badge_text = "ESTIMATE - NOT A TAX INVOICE" if is_quote else "AWAITING PAYMENT"
    badge_gold = is_quote                          # gold border only for invoice

    client  = state.get("client_name", "Client")
    email   = state.get("email", "")
    evt     = state.get("event_type", "Event")
    date_s  = _fmt_date_range(state.get("dates"))
    rooms_s = _fmt_rooms(state.get("rooms"))
    reference = f"{invoice_number} · {client.split()[0].upper()}" if invoice_number else ""

    buf = io.BytesIO()
    c   = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    L = 50; R = W - 50; CW = R - L

    # ── helpers ────────────────────────────────────────────────────────────────
    def rule(y, clr=C_LGRAY, t=0.5):
        c.setStrokeColor(clr); c.setLineWidth(t); c.line(L, y, R, y)

    def sf(size, bold=False):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)

    def txt(text, x, y, size=10, color=C_BLACK, bold=False, right=False):
        c.setFillColor(color); sf(size, bold)
        if right:
            c.drawRightString(x, y, str(text))
        else:
            c.drawString(x, y, str(text))

    def lbl(text, x, y):
        txt(text.upper(), x, y, size=7.5, color=C_GRAY)

    def wrap_text(text, x, y, max_w, size=9, line_h=13):
        """Draw wrapped text, return final y."""
        sf(size)
        words = str(text).split()
        buf2 = []
        for w in words:
            test = " ".join(buf2 + [w])
            if c.stringWidth(test, "Helvetica", size) > max_w and buf2:
                c.drawString(x, y, " ".join(buf2))
                y -= line_h
                buf2 = [w]
            else:
                buf2.append(w)
        if buf2:
            c.drawString(x, y, " ".join(buf2))
            y -= line_h
        return y

    # ── PAGE ───────────────────────────────────────────────────────────────────
    y = H - 52

    # ── HEADER BAND: logo (right) + title (left) ───────────────────────────────
    logo_sz = 60
    try:
        from reportlab.lib.utils import ImageReader
        logo_img = ImageReader(_LOGO_PATH)
        c.drawImage(logo_img, R - logo_sz, y - logo_sz + 16,
                    width=logo_sz, height=logo_sz, mask="auto")
    except Exception:
        pass  # logo not critical

    c.setFillColor(C_BLACK); c.setFont("Times-Bold", 36)
    c.drawString(L, y, doc_title)

    # Status badge — sits 10pt below the title baseline
    bw, bh = (210, 20) if is_quote else (160, 20)
    by = y - 38
    c.setStrokeColor(C_GOLD if badge_gold else C_LGRAY)
    c.setLineWidth(1.4 if badge_gold else 0.8)
    c.rect(L, by, bw, bh, stroke=1, fill=0)
    c.setFillColor(C_GOLD if badge_gold else C_GRAY)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(L + bw / 2, by + 6, badge_text)

    y -= 72   # clear title + badge + gap before company block

    # ── COMPANY / META two-column block ───────────────────────────────────────
    mx_l = R - 150; mx_r = R
    ROW = 16   # line height for company block rows
    if invoice_number:
        txt(COMPANY_NAME, L, y, bold=True)
        txt("Invoice", mx_l, y, size=9, color=C_GRAY)
        txt(invoice_number, mx_r, y, size=9, bold=True, right=True)
        y -= ROW
        txt(COMPANY_ADDR, L, y, size=9, color=C_GRAY)
        txt("Issued", mx_l, y, size=9, color=C_GRAY)
        txt(issued_date.strftime("%-d %B %Y"), mx_r, y, size=9, bold=True, right=True)
        y -= ROW
        txt(f"{COMPANY_KVK} · {COMPANY_BTW}", L, y, size=9, color=C_GRAY)
        txt("Due date", mx_l, y, size=9, color=C_GRAY)
        txt(due_date.strftime("%-d %B %Y"), mx_r, y, size=9, bold=True, right=True)
    else:
        txt(COMPANY_NAME, L, y, bold=True)
        txt("Prepared", mx_l, y, size=9, color=C_GRAY)
        txt(issued_date.strftime("%-d %B %Y"), mx_r, y, size=9, bold=True, right=True)
        y -= ROW
        txt(COMPANY_ADDR, L, y, size=9, color=C_GRAY)
        txt("Valid for", mx_l, y, size=9, color=C_GRAY)
        txt("7 days", mx_r, y, size=9, bold=True, right=True)
        y -= ROW
        txt(f"{COMPANY_KVK} · {COMPANY_BTW}", L, y, size=9, color=C_GRAY)
    y -= ROW
    txt(f"IBAN: {COMPANY_IBAN}", L, y, size=9, color=C_GRAY)
    y -= 10
    rule(y, clr=C_LGRAY, t=0.4)
    y -= 28

    # ── BILL TO box ────────────────────────────────────────────────────────────
    bill_rows  = 2 if email else 1          # name + optional email
    bx_h       = 28 + bill_rows * 18 + 16  # top pad + rows + bottom pad
    box_top    = y + 8
    box_bottom = box_top - bx_h
    c.setFillColor(C_BG); c.setStrokeColor(colors.HexColor("#e8e4de")); c.setLineWidth(0.5)
    c.rect(L, box_bottom, CW, bx_h, stroke=1, fill=1)
    c.setFillColor(colors.HexColor("#c8c4bc")); c.rect(L, box_bottom, 3, bx_h, stroke=0, fill=1)

    lbl("BILL TO", L + 12, y + 4)
    y -= 18
    txt(client, L + 12, y, size=11, bold=True)
    if email:
        y -= 17
        txt(email, L + 12, y, size=9, color=C_GRAY)
    y -= 32

    # ── DESCRIPTION ────────────────────────────────────────────────────────────
    lbl("DESCRIPTION", L, y); y -= 6; rule(y); y -= 14
    desc_text = (
        f"{evt} at Sauvage Space"
        + (f" · {date_s}" if date_s else "")
        + (f". Spaces: {rooms_s}." if rooms_s else ".")
        + f"  Invoiced by {COMPANY_NAME} on behalf of Sauvage DAO."
    )
    c.setFillColor(C_BLACK); sf(10)
    y = wrap_text(desc_text, L, y, CW, size=10, line_h=16)
    y -= 20

    # ── LINE ITEMS table ───────────────────────────────────────────────────────
    lbl("LINE ITEMS", L, y); y -= 6; rule(y); y -= 6

    # Column widths (sum = CW)
    raw_widths = [185, 38, 70, 34, 63, 56, 70]
    scale = CW / sum(raw_widths)
    cw = [w * scale for w in raw_widths]
    hdrs = ["DESCRIPTION", "QTY", "UNIT INCL", "VAT", "LINE EX VAT", "VAT AMT", "LINE INCL"]
    HDR_H = 22

    def draw_row_bg(row_y, row_h, bg):
        c.setFillColor(bg); c.setStrokeColor(colors.HexColor("#e8e4de")); c.setLineWidth(0.3)
        c.rect(L, row_y - row_h + 4, CW, row_h, stroke=1, fill=1)

    def draw_cells(cols, row_y, row_h, bold=False, size=8.5, italic=False):
        xs = L
        text_y = row_y - (row_h / 2) - 3   # vertically centred
        for i, (val, w) in enumerate(zip(cols, cw)):
            c.setFillColor(C_BLACK); sf(size, bold)
            if italic:
                c.setFont("Helvetica-Oblique", size)
            if i == 0:
                c.drawString(xs + 5, text_y, str(val))
            else:
                c.drawRightString(xs + w - 4, text_y, str(val))
            xs += w

    # Header row
    draw_row_bg(y, HDR_H, colors.HexColor("#e8e4de"))
    draw_cells(hdrs, y, HDR_H, bold=True, size=7.5)
    y -= HDR_H

    for idx, item in enumerate(line_items):
        is_disc = item.get("is_discount")
        desc = item["description"]
        # Measure wrapped description height
        sf(9)
        words = desc.split(); buf3 = []; dlines = []
        for w in words:
            test = " ".join(buf3 + [w])
            if c.stringWidth(test, "Helvetica", 9) > cw[0] - 12 and buf3:
                dlines.append(" ".join(buf3)); buf3 = [w]
            else:
                buf3.append(w)
        if buf3: dlines.append(" ".join(buf3))
        row_h = max(24, len(dlines) * 13 + 10)

        bg = C_WHITE if idx % 2 == 0 else C_BG
        draw_row_bg(y, row_h, bg)

        # Description (multi-line), vertically centred
        c.setFillColor(C_GRAY if is_disc else C_BLACK); sf(9)
        total_text_h = len(dlines) * 13
        dy = y - (row_h - total_text_h) / 2 - 10
        for dl in dlines:
            c.drawString(L + 5, dy, dl); dy -= 13

        # Numeric columns (vertically centred)
        num_y = y - row_h / 2 - 3
        if is_disc:
            vals = ["", "", "", "", "", _money(item["total_incl"])]
        else:
            qty_s   = f"{int(item['qty'])}" if item["qty"] == int(item["qty"]) else f"{item['qty']:.1f}"
            unit_s  = _money(item["unit_incl"]) if item["unit_incl"] >= 0 else ""
            vat_pct = f"{int(item['vat_rate']*100)}%" if not is_disc else ""
            vals = [
                qty_s,
                unit_s,
                vat_pct,
                _money(item["total_ex"]),
                _money(item["vat_amt"]),
                _money(item["total_incl"]),
            ]
        xs = L + cw[0]
        for i, (val, w) in enumerate(zip(vals, cw[1:])):
            c.setFillColor(C_GRAY if is_disc else C_BLACK)
            sf(9, bold=(i == 5 and not is_disc))
            c.drawRightString(xs + w - 4, num_y, val)
            xs += w
        y -= row_h

    y -= 14

    # ── TOTALS ─────────────────────────────────────────────────────────────────
    tx = R - 175; vx = R

    def tot_line(lbl_t, val_t, bold=False, italic=False, top_rule=False, color=C_BLACK):
        nonlocal y
        if top_rule:
            c.setStrokeColor(C_LGRAY); c.setLineWidth(0.5)
            c.line(tx - 10, y + 14, R, y + 14)
        c.setFillColor(C_GRAY if not bold else color)
        if italic: c.setFont("Helvetica-Oblique", 9)
        else: sf(9, bold)
        c.drawString(tx, y, lbl_t)
        c.setFillColor(color); sf(9, bold)
        c.drawRightString(vx, y, val_t)
        y -= 17

    tot_line("Space rental ex VAT", _money(totals["total_ex"]))
    tot_line("VAT (21%)", _money(totals["total_vat"]))
    if totals.get("deposit", 0) > 0:
        tot_line("Refundable deposit (0% VAT)", _money(totals["deposit"]), italic=True)
    if deposit_paid > 0:
        tot_line("Deposit paid", f"- {_money(deposit_paid)}")
        balance = totals["total_due"] - deposit_paid
        tot_line("Total incl VAT", _money(totals["total_inc"]), top_rule=True)
        tot_line("Balance due", _money(balance), bold=True, color=C_BLACK)
    else:
        tot_line("Total incl VAT", _money(totals["total_inc"]), top_rule=True)
        tot_line("Total due", _money(totals["total_due"]), bold=True, color=C_BLACK)

    y -= 24

    if invoice_number:
        # ── PAYMENT DETAILS ────────────────────────────────────────────────────
        lbl("PAYMENT DETAILS", L, y); y -= 6; rule(y); y -= 18
        col2 = L + 130
        for plbl, pval in [
            ("IBAN",         COMPANY_IBAN),
            ("BIC",          COMPANY_BIC),
            ("ACCOUNT NAME", COMPANY_NAME),
            ("REFERENCE",    reference),
            ("DUE DATE",     due_date.strftime("%-d %B %Y")),
        ]:
            txt(plbl, L, y, size=8, color=C_GRAY)
            txt(pval, col2, y, size=9, bold=True)
            y -= 17
        y -= 12

    # ── Notes box ─────────────────────────────────────────────────────────────
    notes = []
    if is_quote:
        notes.append(
            "This is an estimate only - not a tax invoice. "
            "Prices include 21% BTW. A formal invoice will be issued upon payment."
        )
    else:
        notes.append(
            f"This invoice is issued pursuant to the booking agreement between "
            f"{client} and Sauvage Space ({COMPANY_NAME})."
        )
        notes.append("VAT treatment: space rental subject to 21% BTW. Refundable deposits exempt.")

    sf(9)
    note_lines = []
    for note in notes:
        ws = note.split(); lb = []
        for w in ws:
            t = " ".join(lb + [w])
            if c.stringWidth(t, "Helvetica", 9) > CW - 36 and lb:
                note_lines.append(" ".join(lb)); lb = [w]
            else:
                lb.append(w)
        if lb: note_lines.append(" ".join(lb))
        note_lines.append("")
    bh2 = len(note_lines) * 14 + 24
    # Footer occupies y=34–70 — ensure notes box doesn't overlap it
    FOOTER_SAFE = 80
    if y - bh2 + 12 < FOOTER_SAFE:
        y = FOOTER_SAFE + bh2 - 12
    c.setFillColor(C_NOTE); c.setStrokeColor(colors.HexColor("#e8e4de")); c.setLineWidth(0.5)
    c.rect(L, y - bh2 + 12, CW, bh2, stroke=1, fill=1)
    ny = y
    txt("Notes:", L + 12, ny, size=9, bold=True); ny -= 15
    sf(9); c.setFillColor(C_BLACK)
    for nl in note_lines:
        if nl: c.drawString(L + 12, ny, nl)
        ny -= 14

    # ── Footer ─────────────────────────────────────────────────────────────────
    rule(58)
    c.setFont("Helvetica", 7.5); c.setFillColor(C_GRAY)
    c.drawCentredString(W / 2, 46, f"{COMPANY_NAME} · {COMPANY_KVK} · {COMPANY_BTW}")
    c.drawCentredString(W / 2, 34, f"{COMPANY_BEHALF} · {COMPANY_EMAIL}")

    c.save()
    return buf.getvalue()


# ── Public API ─────────────────────────────────────────────────────────────────

def build_quote_pdf(state: dict) -> bytes:
    """
    Generate a proforma quote PDF (no invoice number, 'QUOTE' heading).
    Used by the 'Export as PDF' button in the widget.
    """
    items  = compute_line_items(state)
    totals = _sum_items(items)
    return _render_pdf(state, items, totals)


def build_invoice(
    state:          dict,
    deposit_paid:   float = 0.0,
    record_id:      str = "",
    invoice_number: Optional[str] = None,
    issued_date:    Optional[datetime] = None,
) -> tuple[str, bytes]:
    """
    Generate a numbered invoice PDF.
    Returns (invoice_number, pdf_bytes).
    """
    if issued_date is None:
        issued_date = datetime.now()
    if invoice_number is None:
        invoice_number = next_invoice_number(issued_date.year)
    items  = compute_line_items(state)
    totals = _sum_items(items)
    pdf    = _render_pdf(state, items, totals,
                         invoice_number=invoice_number,
                         issued_date=issued_date,
                         deposit_paid=deposit_paid,
                         record_id=record_id)
    return invoice_number, pdf


# ── File persistence ───────────────────────────────────────────────────────────

def save_invoice(invoice_number: str, pdf_bytes: bytes) -> str:
    os.makedirs(_INV_DIR, exist_ok=True)
    path = os.path.join(_INV_DIR, f"{invoice_number}.pdf")
    with open(path, "wb") as f:
        f.write(pdf_bytes)
    print(f"[Invoice] Saved → {path}")
    return path


def invoice_url(invoice_number: str, base_url: str = "") -> str:
    if not base_url:
        base_url = os.getenv("BASE_URL", "https://sauvage.amsterdam")
    import hmac as _hmac, hashlib as _hl
    secret = os.getenv("INVOICE_SECRET", "sauvage-invoice-secret")
    token  = _hmac.new(secret.encode(), invoice_number.encode(), _hl.sha256).hexdigest()[:24]
    return f"{base_url}/invoice/{invoice_number}?t={token}"


def verify_invoice_token(invoice_number: str, token: str) -> bool:
    import hmac as _hmac, hashlib as _hl
    secret   = os.getenv("INVOICE_SECRET", "sauvage-invoice-secret")
    expected = _hmac.new(secret.encode(), invoice_number.encode(), _hl.sha256).hexdigest()[:24]
    return _hmac.compare_digest(expected, token)


# ── Quick test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_state = {
        "client_name": "Carmen Santana",
        "email":       "carmen@fuli.nl",
        "event_type":  "Pop-up",
        "dates":       ["2026-05-18", "2026-05-31"],
        "rooms":       ["Entrance", "Upstairs — Gallery"],
        "duration":    "Hourly",
        "hours":       5,
        "guest_count": 30,
        "addons":      ["Light Snacks Fento", "Event Cleanup"],
        "quote_total": 1000.00,
    }
    # Quote PDF
    pdf_q = build_quote_pdf(test_state)
    with open("/tmp/test-quote.pdf", "wb") as f: f.write(pdf_q)
    print("Quote → /tmp/test-quote.pdf")

    # Invoice PDF
    num, pdf_i = build_invoice(test_state, deposit_paid=50.0)
    save_invoice(num, pdf_i)
    print(f"Invoice {num} → invoices/{num}.pdf")
