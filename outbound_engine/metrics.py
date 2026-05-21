"""
Aggregates outreach metrics across all markets and tabs.
Deduplicates by owner email/phone — fleet owners count once.
Filters out test rows (Notes = "test").
Scans all worksheets automatically — handles custom tab names.

Tabs whose name contains "prospect" (case-insensitive) are counted as
prospect outreach. Everything else with touch columns counts as funnel.
"""

import os
import gspread
from gspread.http_client import BackOffHTTPClient
from google.oauth2.service_account import Credentials

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Each entry: (touch#, email_col, sms_col_candidates)
# sms_col_candidates is a tuple so we can handle legacy column name variants
# (e.g. "SMS1" without a space, used in the Keys market's n8n-era Prospects tab)
_TOUCH_COLS = [
    (1, "Email 1", ("SMS 1", "SMS1")),
    (2, "Email 2", ("SMS 2",)),
    (3, "Email 3", ("SMS 3",)),
]

# Candidate columns for owner identification, tried in priority order
_EMAIL_CANDIDATES = ["OWNER_EMAIL", "Email"]
_PHONE_CANDIDATES = ["OWNER_PHONE_NUMBER", "Phone Number", "Phone"]

# Skip tabs by prefix or exact name — non-outreach data
_SKIP_PREFIXES = ("_",)
_SKIP_NAMES    = {"SQL", "Segments", "Schedule", "Kustomer ID", "Warm Leads", "Wins"}


def _open_client():
    creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    if not creds_path:
        return None
    creds = Credentials.from_service_account_file(creds_path, scopes=_SCOPES)
    return gspread.Client(auth=creds, http_client=BackOffHTTPClient)


def _empty() -> dict:
    return {
        "emails":    {1: 0, 2: 0, 3: 0},
        "sms":       {1: 0, 2: 0, 3: 0},
        "contacted": 0,
        "replied":   0,
    }


def _merge(a: dict, b: dict) -> dict:
    return {
        "emails":    {t: a["emails"][t] + b["emails"][t] for t in (1, 2, 3)},
        "sms":       {t: a["sms"][t]    + b["sms"][t]    for t in (1, 2, 3)},
        "contacted": a["contacted"] + b["contacted"],
        "replied":   a["replied"]   + b["replied"],
    }


def _aggregate_tab(rows: list[dict], email_col: str | None, phone_col: str | None) -> dict:
    seen   = set()
    result = _empty()

    for row in rows:
        if str(row.get("Notes", "") or "").strip().lower() == "test":
            continue

        email = str(row.get(email_col, "") or "").strip().lower() if email_col else ""
        phone = str(row.get(phone_col, "") or "").strip()         if phone_col else ""
        key   = email if email else phone
        if not key or key in seen:
            continue
        seen.add(key)

        has_send = False
        for touch, e_col, s_cols in _TOUCH_COLS:
            if str(row.get(e_col, "") or "").strip():
                result["emails"][touch] += 1
                has_send = True
            if any(str(row.get(c, "") or "").strip() for c in s_cols):
                result["sms"][touch] += 1
                has_send = True

        if has_send:
            result["contacted"] += 1

        if str(row.get("Replied?", "") or "").strip().lower() == "true":
            result["replied"] += 1

    return result


def _tab_category(tab_name: str) -> str:
    """Returns 'prospect' if the tab is a Prospects tab, 'funnel' otherwise."""
    return "prospect" if "prospect" in tab_name.lower() else "funnel"


def _try_aggregate_worksheet(ws) -> tuple[str, dict] | None:
    """
    Reads a worksheet, auto-detects owner ID columns, and returns (category, aggregated metrics).
    Returns None if the tab should be skipped (utility tab, no touch columns, no ID columns).
    """
    name = ws.title
    if any(name.startswith(p) for p in _SKIP_PREFIXES) or name in _SKIP_NAMES:
        return None

    try:
        rows = ws.get_all_records()
    except Exception:
        return None

    if not rows:
        return None

    headers = set(rows[0].keys())

    # Only process tabs that have at least one touch timestamp column
    if not any(c in headers for c in ["Email 1", "SMS 1"]):
        return None

    email_col = next((c for c in _EMAIL_CANDIDATES if c in headers), None)
    phone_col = next((c for c in _PHONE_CANDIDATES if c in headers), None)

    if not email_col and not phone_col:
        return None

    return _tab_category(name), _aggregate_tab(rows, email_col, phone_col)


def load_all_metrics(markets: dict) -> dict:
    """
    Reads all market sheets and returns separate funnel and prospect aggregations:

      {
        "funnel": {
          "total":   { emails, sms, contacted, replied },
          "markets": { market_key: { display_name, emails, sms, contacted, replied } }
        },
        "prospect": {
          "total":   { emails, sms, contacted, replied },
          "markets": { market_key: { display_name, emails, sms, contacted, replied } }
        },
      }

    A market only appears in a category's "markets" dict if it has at least one send
    in that category. Markets with both funnel and prospect data appear in both.
    """
    client = _open_client()
    if not client:
        return {
            "funnel":   {"total": _empty(), "markets": {}},
            "prospect": {"total": _empty(), "markets": {}},
        }

    funnel_total   = _empty()
    prospect_total = _empty()
    funnel_mkts    = {}
    prospect_mkts  = {}

    for market_key, market in markets.items():
        sheet_id     = market["sheet_id"]
        display_name = market["display_name"]
        funnel_agg   = _empty()
        prospect_agg = _empty()

        try:
            ss = client.open_by_key(sheet_id)
        except Exception:
            continue

        for ws in ss.worksheets():
            result = _try_aggregate_worksheet(ws)
            if result is None:
                continue
            category, tab_agg = result
            if category == "prospect":
                prospect_agg = _merge(prospect_agg, tab_agg)
            else:
                funnel_agg = _merge(funnel_agg, tab_agg)

        if funnel_agg["contacted"] > 0 or sum(funnel_agg["emails"].values()) > 0:
            funnel_mkts[market_key] = {"display_name": display_name, **funnel_agg}
            funnel_total = _merge(funnel_total, funnel_agg)

        if prospect_agg["contacted"] > 0 or sum(prospect_agg["emails"].values()) > 0:
            prospect_mkts[market_key] = {"display_name": display_name, **prospect_agg}
            prospect_total = _merge(prospect_total, prospect_agg)

    return {
        "funnel":   {"total": funnel_total,   "markets": funnel_mkts},
        "prospect": {"total": prospect_total, "markets": prospect_mkts},
    }
