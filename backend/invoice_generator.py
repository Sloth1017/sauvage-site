"""
invoice_generator.py
--------------------
Generates PDF invoices for Sauvage bookings in the style of RNR-2026-NNN.
Issued by Roots & Remedies Stichting on behalf of Sauvage DAO.

Usage:
    from invoice_generator import build_invoice, next_invoice_number
    invoice_num, pdf_bytes = build_invoice(state, deposit_amount, record_id)
"""

import io
import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Constants ──────────────────────────────────────────────────────────────────
COMPANY_NAME    = "Roots & Remedies Stichting"
COMPANY_ADDR    = "Potgieterstraat 47 H · 1053XS Amsterdam · Netherlands"
COMPANY_KVK     = "KvK: 76681629"
COMPANY_BTW     = "BTW: NL860744875B01"
COMPANY_IBAN    = "NL42 TRIO 0788 8783 60"
COMPANY_BIC     = "TRIONL2U"
COMPANY_EMAIL   = "hello@rootsandremedies.earth"
COMPANY_BEHALF  = "Issued on behalf of Sauvage DAO"

VAT_RATE        = 0.21
DUE_DAYS        = 7          # invoice due N days after issue

_DB_PATH        = os.path.join(os.path.dirname(__file__), "sessions.db")
_INV_DIR        = os.path.join(os.path.dirname(__file__), "invoices")

# Colours matching the sample
C_BLACK  = colors.HexColor("#1a1a1a")
C_GOLD   = colors.HexColor("#b8860b")
C_GRAY   = colors.HexColor("#888888")
C_LGRAY  = colors.HexColor("#cccccc")
C_BGROW  = colors.HexColor("#f5f3ef")
C_NOTE   = colors.HexColor("#faf8f0")
C_WHITE  = colors.white


# ── Invoice number counter ─────────────────────────────────────────────────────

def next_invoice_number(year: Optional[int] = None) -> str:
    """
    Auto-increment RNR-YYYY-NNN counter stored in sessions.db.
    Returns e.g. 'RNR-2026-007'.
    """
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


# ── Data helpers ───────────────────────────────────────────────────────────────

def _fmt_date_range(dates) -> str:
    """Return a human-readable date string from a date or list of dates."""
    if not dates:
        return ""
    if isinstance(dates, list) and len(dates) >= 2:
        try:
            d0 = datetime.strptime(str(dates[0]).strip(), "%Y-%m-%d")
            d1 = datetime.strptime(str(dates[-1]).strip(), "%Y-%m-%d")
            if d0.month == d1.month:
                return f"{d0.day}–{d1.day} {d0.strftime('%B %Y')}"
            return f"{d0.strftime('%-d %b')}–{d1.strftime('%-d %b %Y')}"
        except ValueError:
            return f"{dates[0]}–{dates[-1]}"
    if isinstance(dates, list):
        return str(dates[0])
    # Single string — try to parse
    try:
        d = datetime.strptime(str(dates).strip(), "%Y-%m-%d")
        return d.strftime("%-d %B %Y")
    except ValueError:
        return str(dates)


def _fmt_rooms(rooms) -> str:
    if not rooms:
        return "Sauvage Space"
    if isinstance(rooms, list):
        return " + ".join(r for r in rooms)
    return str(rooms)


def _parse_quote(state: dict) -> dict:
    """
    Return a dict with: total_incl, total_ex, vat_amt,
    deposit_ex (0% VAT kitchen deposit), total_due.
    """
    qt = float(state.get("quote_total") or 0)
    # Kitchen deposit: refundable, 0% VAT
    rooms_lower = str(state.get("rooms", "")).lower()
    kitchen_dep = 500.0 if "kitchen" in rooms_lower else 0.0

    # Space rental is quote_total incl 21% VAT
    rental_ex  = round(qt / (1 + VAT_RATE), 2)
    vat_amt    = round(qt - rental_ex, 2)

    # Add-on line items parsed from addons list
    addon_lines = _parse_addon_lines(state)

    return {
        "rental_incl":  qt,
        "rental_ex":    rental_ex,
        "vat_amt":      vat_amt,
        "kitchen_dep":  kitchen_dep,
        "addon_lines":  addon_lines,
        "total_due":    round(qt + kitchen_dep, 2),
    }


def _parse_addon_lines(state: dict) -> list[dict]:
    """
    Return extra line items for notable add-ons (Fento, Staff, etc.)
    that are already factored into quote_total — listed for transparency.
    """
    # For now we list add-ons informatively but they're included in quote_total
    addons = state.get("addons") or []
    if isinstance(addons, str):
        addons = [addons]
    lines = []
    for a in addons:
        lines.append({"description": a, "note": "included in space rental"})
    return lines


# ── PDF builder ────────────────────────────────────────────────────────────────

def build_invoice(
    state:          dict,
    deposit_paid:   float = 0.0,
    record_id:      str = "",
    invoice_number: Optional[str] = None,
    issued_date:    Optional[datetime] = None,
) -> tuple[str, bytes]:
    """
    Build a PDF invoice.
    Returns (invoice_number, pdf_bytes).
    """
    if issued_date is None:
        issued_date = datetime.now()
    due_date = issued_date + timedelta(days=DUE_DAYS)

    if invoice_number is None:
        invoice_number = next_invoice_number(issued_date.year)

    q       = _parse_quote(state)
    client  = state.get("client_name", "Client")
    email   = state.get("email", "")
    evt     = state.get("event_type", "Event")
    date_s  = _fmt_date_range(state.get("dates"))
    rooms_s = _fmt_rooms(state.get("rooms"))

    # Reference on payment slip: "RNR-2026-007 · {client}"
    reference = f"{invoice_number} · {client.split()[0].upper()}"

    buf = io.BytesIO()
    c   = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4                      # 595.28 × 841.89

    L = 50                         # left margin
    R = W - 50                     # right margin
    CW = R - L                     # content width

    # ── Helpers ──────────────────────────────────────────────────────────────

    def setf(name, size, bold=False):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)

    def rule(y, color=C_LGRAY, thickness=0.5):
        c.setStrokeColor(color)
        c.setLineWidth(thickness)
        c.line(L, y, R, y)

    def label(text, x, y, size=8, color=C_GRAY):
        c.setFillColor(color)
        setf("Helvetica", size)
        c.drawString(x, y, text.upper())

    def body(text, x, y, size=10, color=C_BLACK, bold=False):
        c.setFillColor(color)
        setf("Helvetica", size, bold=bold)
        c.drawString(x, y, text)

    def rbody(text, x, y, size=10, color=C_BLACK, bold=False):
        c.setFillColor(color)
        setf("Helvetica", size, bold=bold)
        c.drawRightString(x, y, text)

    def money(v: float) -> str:
        return f"€ {v:,.2f}".replace(",", "\xa0")   # thin-space thousands

    # ── Page 1 ──────────────────────────────────────────────────────────────

    y = H - 50

    # INVOICE heading
    c.setFillColor(C_BLACK)
    c.setFont("Times-Bold", 32)
    c.drawString(L, y, "INVOICE")

    # Status badge — gold border box
    badge_w, badge_h = 148, 22
    badge_x = R - badge_w
    badge_y = y - 4
    c.setStrokeColor(C_GOLD)
    c.setLineWidth(1.2)
    c.rect(badge_x, badge_y, badge_w, badge_h, stroke=1, fill=0)
    c.setFillColor(C_GOLD)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(badge_x + badge_w / 2, badge_y + 7, "AWAITING PAYMENT")

    y -= 28

    # Company details (left) + invoice meta (right)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(C_BLACK)
    c.drawString(L, y, COMPANY_NAME)

    # Invoice meta labels (right column)
    meta_lx = R - 140
    meta_vx = R
    c.setFont("Helvetica", 9)
    c.setFillColor(C_GRAY)
    c.drawString(meta_lx, y, "Invoice")
    c.setFillColor(C_BLACK)
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(meta_vx, y, invoice_number)

    y -= 14
    c.setFont("Helvetica", 9)
    c.setFillColor(C_GRAY)
    c.drawString(L, y, COMPANY_ADDR)
    c.drawString(meta_lx, y, "Issued")
    c.setFillColor(C_BLACK)
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(meta_vx, y, issued_date.strftime("%-d %B %Y"))

    y -= 14
    c.setFont("Helvetica", 9)
    c.setFillColor(C_GRAY)
    c.drawString(L, y, f"{COMPANY_KVK} · {COMPANY_BTW}")
    c.drawString(meta_lx, y, "Due date")
    c.setFillColor(C_BLACK)
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(meta_vx, y, due_date.strftime("%-d %B %Y"))

    y -= 14
    c.setFont("Helvetica", 9)
    c.setFillColor(C_GRAY)
    c.drawString(L, y, f"IBAN: {COMPANY_IBAN}")

    y -= 28

    # BILL TO box
    box_h = 52
    c.setFillColor(C_BGROW)
    c.setStrokeColor(colors.HexColor("#e8e4de"))
    c.setLineWidth(0.5)
    c.rect(L, y - box_h + 14, CW, box_h, stroke=1, fill=1)

    # left accent bar
    c.setFillColor(colors.HexColor("#c8c4bc"))
    c.rect(L, y - box_h + 14, 3, box_h, stroke=0, fill=1)

    label("BILL TO", L + 10, y + 4, size=7.5, color=C_GRAY)
    y -= 14
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(C_BLACK)
    c.drawString(L + 10, y, client)
    if email:
        y -= 14
        c.setFont("Helvetica", 9)
        c.setFillColor(C_GRAY)
        c.drawString(L + 10, y, email)

    y -= 26

    # DESCRIPTION section
    label("DESCRIPTION", L, y, size=7.5)
    y -= 4
    rule(y)
    y -= 16

    # Description paragraph (multi-line wrapping)
    desc = (
        f"{evt} at Sauvage Space"
        + (f" · {date_s}" if date_s else "") + "."
    )
    if rooms_s:
        desc += f"  Spaces: {rooms_s}."
    desc += f"  Invoiced by {COMPANY_NAME} on behalf of Sauvage DAO."

    c.setFont("Helvetica", 10)
    c.setFillColor(C_BLACK)
    # Simple word-wrap
    max_w = CW
    words = desc.split()
    line_buf = []
    line_h = 15
    for word in words:
        test = " ".join(line_buf + [word])
        if c.stringWidth(test, "Helvetica", 10) > max_w and line_buf:
            c.drawString(L, y, " ".join(line_buf))
            y -= line_h
            line_buf = [word]
        else:
            line_buf.append(word)
    if line_buf:
        c.drawString(L, y, " ".join(line_buf))
        y -= line_h

    y -= 14

    # LINE ITEMS section
    label("LINE ITEMS", L, y, size=7.5)
    y -= 4
    rule(y)
    y -= 4

    # Table header
    col_widths = [200, 28, 72, 36, 65, 58, 72]  # sum ≈ 531 → trim to CW
    scale = CW / sum(col_widths)
    cw = [w * scale for w in col_widths]

    headers = ["DESCRIPTION", "QTY", "UNIT EX VAT", "VAT", "LINE EX VAT", "VAT AMT", "LINE INCL VAT"]
    hdr_h   = 22

    def draw_row(cols, x_start, row_y, row_h, bg=None, bold=False, size=9):
        if bg:
            c.setFillColor(bg)
            c.setStrokeColor(colors.HexColor("#e8e4de"))
            c.setLineWidth(0.3)
            c.rect(x_start, row_y - row_h + 4, CW, row_h, stroke=1, fill=1)
        xs = x_start
        for i, (text, w) in enumerate(zip(cols, cw)):
            c.setFillColor(C_BLACK)
            c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
            if i == 0:
                c.drawString(xs + 4, row_y - row_h + 8, str(text))
            else:
                c.drawRightString(xs + w - 4, row_y - row_h + 8, str(text))
            xs += w

    draw_row(headers, L, y, hdr_h, bg=C_BGROW, bold=True, size=8)
    y -= hdr_h

    # Rental line item
    rental_desc = f"Space rental — {rooms_s}"
    if date_s:
        rental_desc += f" · {date_s}"
    rental_row = [
        rental_desc, "1",
        money(q["rental_ex"]),
        "21%",
        money(q["rental_ex"]),
        money(q["vat_amt"]),
        money(q["rental_incl"]),
    ]
    # Multi-line rental description
    desc_words = rental_desc.split()
    desc_lines = []
    buf2 = []
    for w in desc_words:
        test2 = " ".join(buf2 + [w])
        if c.stringWidth(test2, "Helvetica", 9) > cw[0] - 10 and buf2:
            desc_lines.append(" ".join(buf2))
            buf2 = [w]
        else:
            buf2.append(w)
    if buf2:
        desc_lines.append(" ".join(buf2))
    item_h = max(20, len(desc_lines) * 14 + 10)

    # Draw row bg
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#e8e4de"))
    c.setLineWidth(0.3)
    c.rect(L, y - item_h + 4, CW, item_h, stroke=1, fill=1)

    # Description column (multi-line)
    c.setFillColor(C_BLACK)
    c.setFont("Helvetica", 9)
    dl_y = y - 8
    for dl in desc_lines:
        c.drawString(L + 4, dl_y, dl)
        dl_y -= 13
    # Sub-note in gray
    c.setFont("Helvetica", 7.5)
    c.setFillColor(C_GRAY)
    c.drawString(L + 4, dl_y, "Invoiced on behalf of Sauvage DAO")

    # Numeric columns
    xs = L + cw[0]
    for i, (text, w) in enumerate(zip(rental_row[1:], cw[1:])):
        c.setFillColor(C_BLACK)
        c.setFont("Helvetica", 9)
        c.drawRightString(xs + w - 4, y - item_h + 10, text)
        xs += w
    y -= item_h

    # Kitchen deposit line (if applicable)
    if q["kitchen_dep"] > 0:
        dep_row = [
            "Kitchen deposit — refundable upon satisfactory completion",
            "1",
            money(q["kitchen_dep"]),
            "0%",
            money(q["kitchen_dep"]),
            money(0.0),
            money(q["kitchen_dep"]),
        ]
        draw_row(dep_row, L, y, 22, bg=C_BGROW, size=9)
        y -= 22

    y -= 16

    # ── Totals block (right-aligned) ────────────────────────────────────────
    tx = R - 160   # label start
    vx = R         # value right-align

    def tot_row(lbl, val, bold=False, italic=False, top_rule=False):
        nonlocal y
        if top_rule:
            c.setStrokeColor(C_LGRAY)
            c.setLineWidth(0.5)
            c.line(tx - 10, y + 12, R, y + 12)
        c.setFillColor(C_GRAY if not bold else C_BLACK)
        if italic:
            c.setFont("Helvetica-Oblique", 9)
        else:
            c.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
        c.drawString(tx, y, lbl)
        c.setFillColor(C_BLACK)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
        c.drawRightString(vx, y, val)
        y -= 14

    tot_row(f"Space rental ex VAT", money(q["rental_ex"]))
    tot_row(f"VAT (21%)", money(q["vat_amt"]))
    tot_row("Space rental incl VAT", money(q["rental_incl"]))
    if q["kitchen_dep"] > 0:
        tot_row("Kitchen deposit (excl VAT)", money(q["kitchen_dep"]), italic=True)
    if deposit_paid > 0:
        tot_row(f"Deposit paid", f"- {money(deposit_paid)}")
        balance = q["total_due"] - deposit_paid
        tot_row("Total due", money(balance), bold=True, top_rule=True)
    else:
        tot_row("Total due", money(q["total_due"]), bold=True, top_rule=True)

    y -= 20

    # ── PAYMENT DETAILS ──────────────────────────────────────────────────────
    label("PAYMENT DETAILS", L, y, size=7.5)
    y -= 4
    rule(y)
    y -= 18

    pay_rows = [
        ("IBAN",         COMPANY_IBAN),
        ("BIC",          COMPANY_BIC),
        ("ACCOUNT NAME", COMPANY_NAME),
        ("REFERENCE",    reference),
        ("DUE DATE",     due_date.strftime("%-d %B %Y")),
    ]
    lbl_x = L
    val_x = L + 120
    for plbl, pval in pay_rows:
        c.setFont("Helvetica", 8)
        c.setFillColor(C_GRAY)
        c.drawString(lbl_x, y, plbl)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(C_BLACK)
        c.drawString(val_x, y, pval)
        y -= 16

    y -= 10

    # ── Notes box ────────────────────────────────────────────────────────────
    notes = []
    if q["kitchen_dep"] > 0:
        notes.append(
            f"Kitchen deposit of {money(q['kitchen_dep'])} is refundable upon "
            f"satisfactory completion of the booking."
        )
    notes.append(
        f"This invoice is issued pursuant to the booking agreement between "
        f"{client} and Sauvage Space ({COMPANY_NAME})."
    )
    notes.append(
        "VAT treatment: space rental fee subject to 21% BTW. "
        + ("Kitchen deposit exempt." if q["kitchen_dep"] > 0 else "")
    )

    # Measure notes height
    note_lines = []
    for note in notes:
        ws = note.split()
        lb = []
        for w in ws:
            t = " ".join(lb + [w])
            if c.stringWidth(t, "Helvetica", 9) > CW - 30 and lb:
                note_lines.append(" ".join(lb))
                lb = [w]
            else:
                lb.append(w)
        if lb:
            note_lines.append(" ".join(lb))
        note_lines.append("")  # gap between paragraphs

    box_height = len(note_lines) * 13 + 18
    c.setFillColor(C_NOTE)
    c.setStrokeColor(colors.HexColor("#e8e4de"))
    c.setLineWidth(0.5)
    c.rect(L, y - box_height + 10, CW, box_height, stroke=1, fill=1)

    ny = y - 2
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(C_BLACK)
    c.drawString(L + 10, ny, "Notes:")
    ny -= 13
    c.setFont("Helvetica", 9)
    for nl in note_lines:
        if nl:
            c.drawString(L + 10, ny, nl)
        ny -= 13

    y = ny - 20

    # ── Footer ────────────────────────────────────────────────────────────────
    rule(60)
    c.setFont("Helvetica", 7.5)
    c.setFillColor(C_GRAY)
    footer1 = f"{COMPANY_NAME} · {COMPANY_KVK} · {COMPANY_BTW}"
    footer2 = f"{COMPANY_BEHALF} · {COMPANY_EMAIL}"
    c.drawCentredString(W / 2, 48, footer1)
    c.drawCentredString(W / 2, 36, footer2)

    c.save()
    return invoice_number, buf.getvalue()


# ── File persistence ───────────────────────────────────────────────────────────

def save_invoice(invoice_number: str, pdf_bytes: bytes) -> str:
    """Save PDF to disk and return the file path."""
    os.makedirs(_INV_DIR, exist_ok=True)
    path = os.path.join(_INV_DIR, f"{invoice_number}.pdf")
    with open(path, "wb") as f:
        f.write(pdf_bytes)
    print(f"[Invoice] Saved → {path}")
    return path


def invoice_url(invoice_number: str, base_url: str = "") -> str:
    """Return the public URL for an invoice (served by Flask /invoice/ route)."""
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
    sample_state = {
        "client_name": "Carmen Santana",
        "email":       "carmen@fuli.nl",
        "event_type":  "Pop-up",
        "dates":       ["2026-05-18", "2026-05-31"],
        "rooms":       ["Entrance", "Upstairs — Gallery"],
        "guest_count": 30,
        "quote_total": 1000.00,
        "addons":      ["Light Snacks Fento", "Event Cleanup"],
    }
    num, pdf = build_invoice(sample_state, deposit_paid=50.0, record_id="TEST")
    save_invoice(num, pdf)
    print(f"Invoice {num} written to invoices/{num}.pdf")
