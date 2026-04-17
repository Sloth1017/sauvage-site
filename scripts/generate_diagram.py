#!/usr/bin/env python3
"""
generate_diagram.py
-------------------
Reads chatbot-prompt-v2.md and chat_backend.py, calls Claude to extract
the booking flow, and rewrites the Mermaid diagram in flow-diagram.html.

Run manually:     python3 scripts/generate_diagram.py
Run via hook:     triggered automatically by .git/hooks/pre-commit
"""

import os
import sys
import re
import anthropic

REPO_ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_FILE  = os.path.join(REPO_ROOT, "backend", "chatbot-prompt-v2.md")
BACKEND_FILE = os.path.join(REPO_ROOT, "backend", "chat_backend.py")
OUTPUT_FILE  = os.path.join(REPO_ROOT, "flow-diagram.html")

# ── Read source files ─────────────────────────────────────────────────────────

def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# ── Extract widget list from backend ─────────────────────────────────────────

def extract_widgets(backend_src: str) -> str:
    """Pull the _determine_widget function for context."""
    m = re.search(r"def _determine_widget.*?^def ", backend_src, re.DOTALL | re.MULTILINE)
    return m.group(0)[:3000] if m else ""

# ── Ask Claude to generate the Mermaid diagram ────────────────────────────────

AIRTABLE_COLUMNS = """
## Airtable column mapping (Inquiries table)
Each step that collects data maps to one or more of these exact Airtable columns.
Show the column name in square brackets on the node label wherever data is captured.

| Data collected          | Airtable column         |
|------------------------|-------------------------|
| Event type             | Event Type              |
| Date(s)                | Requested Date          |
| Start + end time       | Time Slot               |
| Duration               | Duration                |
| Client name            | Client Name             |
| Email                  | Email                   |
| Phone                  | Phone                   |
| Private / Business     | Customer Type           |
| Guest count            | Guest Count             |
| Rooms selected         | Rooms Requested         |
| Add-ons selected       | Add-Ons                 |
| Quote total (incl VAT) | Total Incl VAT          |
| Quote total (ex VAT)   | Total Ex VAT            |
| VAT amount             | VAT Amount              |
| Referral source        | Referral Source         |
| Attributed host        | Attributed Host         |
| Referred by (person)   | Referred By             |
| Arrival time           | Arrival Time            |
| Deposit collected      | Deposit Collected       |
| Payment reference      | Stripe Payment Reference|
| Funnel position        | Funnel Stage            |
| Booking state          | Booking Status          |
| Community pricing      | Community Pricing       |
"""

SYSTEM = """You are a technical diagram generator. Given a chatbot system prompt,
backend widget logic, and an Airtable column mapping table, produce a single valid
Mermaid flowchart (flowchart TD) that accurately maps the booking conversation flow.

Rules:
- Output ONLY the raw Mermaid code block — no prose, no markdown fences, no explanation
- Cover every step, decision point, branch, and widget trigger
- For EVERY node that captures data, append the Airtable column name(s) in the label
  using this format: Client name\\n→ AT: Client Name
  Use \\n to put the column reference on a second line inside the node
- If a step captures multiple columns, list them: → AT: Email, Phone
- Decision diamonds for branching logic (no Airtable labels on diamonds)
- Do NOT include a "Client wants Cave?" decision node — Cave is a passive mention only
- Distinct style for: happy path nodes, decision nodes, widget nodes, error/hard-stop nodes
- Keep node IDs short and camelCase (no spaces)
- Group the Airtable sync steps in a subgraph called "Airtable_Sync"
- The diagram must be valid Mermaid 10 syntax — test every node ID is unique
"""

def _get_api_key() -> str:
    """
    Return ANTHROPIC_API_KEY from (in order):
    1. Local environment variable
    2. Server .env via SSH (uses id_ed25519_new key)
    """
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key:
        return key
    # Try to pull from the production server
    import subprocess
    try:
        result = subprocess.run(
            ["ssh", "-i", os.path.expanduser("~/.ssh/id_ed25519_new"),
             "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
             "root@31.97.35.5",
             "grep ANTHROPIC_API_KEY /root/sauvage/backend/.env | cut -d= -f2"],
            capture_output=True, text=True, timeout=10
        )
        key = result.stdout.strip()
        if key:
            print("[diagram] Using API key from server .env")
            return key
    except Exception as e:
        print(f"[diagram] Could not fetch API key from server: {e}")
    return ""


def generate_mermaid(prompt_src: str, widget_src: str) -> str:
    api_key = _get_api_key()
    if not api_key:
        print("[diagram] ANTHROPIC_API_KEY not available — skipping diagram update")
        sys.exit(0)

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"## CHATBOT SYSTEM PROMPT\n\n{prompt_src}\n\n"
                f"## WIDGET DETECTION LOGIC\n\n{widget_src}\n\n"
                f"{AIRTABLE_COLUMNS}"
            )
        }]
    )
    return msg.content[0].text.strip()

# ── Inject into HTML ──────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sauvage Booking Flow</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background: #f5f3ef; }}
    header {{
      background: #1a1a1a; color: #fff; padding: 20px 32px;
      display: flex; align-items: center; justify-content: space-between;
      position: sticky; top: 0; z-index: 10;
    }}
    header h1 {{ font-size: 16px; font-weight: 500; letter-spacing: 1px; }}
    header span {{ font-size: 11px; color: #666; letter-spacing: 2px; text-transform: uppercase; }}
    .toolbar {{ display: flex; gap: 10px; }}
    button {{
      background: none; border: 1px solid #444; color: #aaa; padding: 5px 14px;
      font-size: 11px; border-radius: 3px; cursor: pointer; font-family: inherit;
    }}
    button:hover {{ border-color: #fff; color: #fff; }}
    .diagram-wrap {{ padding: 40px; overflow-x: auto; min-height: calc(100vh - 120px); }}
    .mermaid {{ max-width: 100%; }}
    .legend {{
      background: #fff; border-radius: 4px; padding: 20px 28px;
      margin: 0 40px 40px; display: flex; flex-wrap: wrap; gap: 18px;
      font-size: 12px; color: #555;
    }}
    .legend h3 {{ width: 100%; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; color: #999; margin-bottom: 4px; }}
    .l-item {{ display: flex; align-items: center; gap: 7px; }}
    .l-dot {{ width: 12px; height: 12px; border-radius: 2px; flex-shrink: 0; }}
    .updated {{ font-size: 10px; color: #999; padding: 8px 40px 16px; text-align: right; }}
    @media print {{ header button {{ display: none; }} }}
  </style>
</head>
<body>
  <header>
    <div>
      <span>Sauvage Amsterdam</span>
      <h1>Booking Chatbot — Decision Flow</h1>
    </div>
    <div class="toolbar">
      <button onclick="window.print()">Print / PDF</button>
      <button onclick="location.reload()">Refresh</button>
    </div>
  </header>

  <div class="diagram-wrap">
    <div class="mermaid">
{mermaid}
    </div>
  </div>

  <div class="legend">
    <h3>Legend</h3>
    <div class="l-item"><div class="l-dot" style="background:#fff;border:1px solid #ccc;"></div>Happy path step</div>
    <div class="l-item"><div class="l-dot" style="background:#f5f3ef;border:1px solid #ccc;"></div>Decision / branch</div>
    <div class="l-item"><div class="l-dot" style="background:#e8f0fe;"></div>Widget triggered</div>
    <div class="l-item"><div class="l-dot" style="background:#e6f4ea;"></div>Airtable sync</div>
    <div class="l-item"><div class="l-dot" style="background:#ffeeee;"></div>Warning / hard stop</div>
    <div class="l-item"><div class="l-dot" style="background:#1a1a1a;"></div>Terminal node</div>
  </div>

  <div class="updated">Auto-generated {timestamp} · source: chatbot-prompt-v2.md</div>

  <script>
    mermaid.initialize({{ startOnLoad: true, theme: 'neutral', flowchart: {{ curve: 'basis', padding: 20 }} }});
  </script>
</body>
</html>
"""

def write_html(mermaid_src: str) -> None:
    from datetime import datetime
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")
    html = HTML_TEMPLATE.format(mermaid=mermaid_src, timestamp=timestamp)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[diagram] Written → {OUTPUT_FILE}")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[diagram] Reading source files…")
    prompt_src  = read_file(PROMPT_FILE)
    backend_src = read_file(BACKEND_FILE)
    widget_src  = extract_widgets(backend_src)

    print("[diagram] Calling Claude to generate diagram…")
    mermaid_src = generate_mermaid(prompt_src, widget_src)

    print("[diagram] Writing HTML…")
    write_html(mermaid_src)
    print("[diagram] Done.")
