"""
Aggregates outreach metrics across all markets and tabs.
Deduplicates by owner email/phone — fleet owners count once.
Filters out test rows (Notes = "test").
"""

import os
import gspread
from gspread.http_client import BackOffHTTPClient
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

_TOUCH_COLS = [
    (1, "Email 1", "SMS 1"),
    (2, "Email 2", "SMS 2"),
    (3, "Email 3", "SMS 3"),
]

# (tab_key, email_col, phone_col)
_TABS = [
    ("bs_live",     "OWNER_EMAIL",   "OWNER_PHONE_NUMBER"),
    ("gmb_live",    "OWNER_EMAIL",   "OWNER_PHONE_NUMBER"),
    ("bs_not_live", "OWNER_EMAIL",   "OWNER_PHONE_NUMBER"),
    ("prospects",   "Email",         "Phone Number"),
]

# Normalize known capitalization inconsistencies across sheets
_NORMALIZE_STATUS = {
    "Not interested": "Not Interested",
}


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
        "by_status": {},
    }


def _merge(a: dict, b: dict) -> dict:
    merged_status = dict(a["by_status"])
    for k, v in b["by_status"].items():
        merged_status[k] = merged_status.get(k, 0) + v
    return {
        "emails":    {t: a["emails"][t] + b["emails"][t] for t in (1, 2, 3)},
        "sms":       {t: a["sms"][t]    + b["sms"][t]    for t in (1, 2, 3)},
        "contacted": a["contacted"] + b["contacted"],
        "replied":   a["replied"]   + b["replied"],
        "by_status": merged_status,
    }


def _aggregate_tab(rows: list[dict], email_col: str, phone_col: str) -> dict:
    seen   = set()
    result = _empty()

    for row in rows:
        if str(row.get("Notes", "") or "").strip().lower() == "test":
            continue

        email = str(row.get(email_col, "") or "").strip().lower()
        phone = str(row.get(phone_col, "") or "").strip()
        key   = email if email else phone
        if not key or key in seen:
            continue
        seen.add(key)

        has_send = False
        for touch, e_col, s_col in _TOUCH_COLS:
            if str(row.get(e_col, "") or "").strip():
                result["emails"][touch] += 1
                has_send = True
            if str(row.get(s_col, "") or "").strip():
                result["sms"][touch] += 1
                has_send = True

        if has_send:
            result["contacted"] += 1

        if str(row.get("Replied?", "") or "").strip().lower() == "true":
            result["replied"] += 1

        status = str(row.get("Contact Status", "") or "").strip()
        status = _NORMALIZE_STATUS.get(status, status)
        if status:
            result["by_status"][status] = result["by_status"].get(status, 0) + 1

    return result


def load_all_metrics(markets: dict) -> dict:
    """
    Reads all market sheets and returns:
      {
        "total":   { emails, sms, contacted, replied, by_status },
        "markets": { market_key: { display_name, emails, sms, contacted, replied, by_status } }
      }
    """
    client = _open_client()
    if not client:
        return {"total": _empty(), "markets": {}}

    overall    = _empty()
    per_market = {}

    for market_key, market in markets.items():
        sheet_id   = market["sheet_id"]
        tab_config = market.get("sheets", {})
        mkt_agg    = _empty()

        try:
            ss = client.open_by_key(sheet_id)
        except Exception:
            per_market[market_key] = {"display_name": market["display_name"], **mkt_agg}
            continue

        for tab_key, email_col, phone_col in _TABS:
            tab_name = tab_config.get(tab_key)
            if not tab_name:
                continue
            try:
                ws      = ss.worksheet(tab_name)
                rows    = ws.get_all_records()
                tab_agg = _aggregate_tab(rows, email_col, phone_col)
                mkt_agg = _merge(mkt_agg, tab_agg)
            except WorksheetNotFound:
                continue
            except Exception:
                continue

        per_market[market_key] = {"display_name": market["display_name"], **mkt_agg}
        overall = _merge(overall, mkt_agg)

    return {"total": overall, "markets": per_market}
