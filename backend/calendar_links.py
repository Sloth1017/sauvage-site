"""
calendar_links.py
-----------------
Helpers for generating "Add to Calendar" URLs used in booking emails.

Supports:
  - Google Calendar  (direct URL, opens in browser)
  - Apple / iCal     (ICS download via /calendar.ics backend endpoint)
"""

from datetime import datetime
from urllib.parse import quote, urlencode

LOCATION    = "Potgieterstraat 47H, Amsterdam, Netherlands"
_DAY_NAMES  = {"monday","tuesday","wednesday","thursday","friday","saturday","sunday"}


def _to_cal_dt(date_str: str, time_str: str) -> str:
    """
    Parse human date + time into iCal / Google Calendar datetime string.
    Handles "2026-05-10" + "18:00"          →  "20260510T180000"
    Handles "Saturday 19 April 2026" + "18:00"  →  "20260419T180000"
    Returns "" on parse failure.
    """
    date_str = date_str.strip()
    # ISO format: YYYY-MM-DD
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        return dt.strftime("%Y%m%dT%H%M%S")
    except ValueError:
        pass
    # Human format: "Saturday 19 April 2026" → strip day name first
    tokens = [t.rstrip(",") for t in date_str.split()
              if t.lower().rstrip(",") not in _DAY_NAMES]
    date_clean = " ".join(tokens)
    try:
        dt = datetime.strptime(f"{date_clean} {time_str}", "%d %B %Y %H:%M")
        return dt.strftime("%Y%m%dT%H%M%S")
    except ValueError:
        return ""


def google_calendar_url(title: str, date_str: str, start_time: str,
                        end_time: str, description: str = "") -> str:
    start = _to_cal_dt(date_str, start_time)
    end   = _to_cal_dt(date_str, end_time)
    if not start or not end:
        return ""
    params = (
        f"action=TEMPLATE"
        f"&text={quote(title)}"
        f"&dates={start}/{end}"
        f"&location={quote(LOCATION)}"
        f"&details={quote(description)}"
    )
    return f"https://calendar.google.com/calendar/render?{params}"


def ics_download_url(base_url: str, title: str, date_str: str,
                     start_time: str, end_time: str, description: str = "") -> str:
    start = _to_cal_dt(date_str, start_time)
    end   = _to_cal_dt(date_str, end_time)
    if not start or not end:
        return ""
    params = urlencode({
        "title":       title,
        "start":       start,
        "end":         end,
        "location":    LOCATION,
        "description": description,
    })
    return f"{base_url}/calendar.ics?{params}"
