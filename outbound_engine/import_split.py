"""
Reads the raw Snowflake export from Sheet1 and routes rows to the correct
destination tabs based on platform and IS_CURRENTLY_LIVE_ON_SITE.

Run once per new Snowflake export, before Funnel Prep.
⚠ Clears and rewrites each destination tab — tracking columns from prior
  runs will be lost. Only run this at the start of a new campaign cycle.

Routing:
  BS - Live      : platform=marketplace  AND IS_CURRENTLY_LIVE_ON_SITE=1
  GMB - Live     : platform=gmb          AND IS_CURRENTLY_LIVE_ON_SITE=1
  BS - Not Live  : platform=marketplace  AND IS_CURRENTLY_LIVE_ON_SITE=0
                   AND BOAT_LISTING_STATE in ACTIONABLE_STATES
  BS - Churn     : platform=marketplace  AND IS_CURRENTLY_LIVE_ON_SITE=0
                   AND BOAT_LISTING_STATE in CHURN_STATES
  GMB - Not Live : platform=gmb          AND IS_CURRENTLY_LIVE_ON_SITE=0
"""

import os

import gspread
import gspread.exceptions
from gspread.http_client import BackOffHTTPClient
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

COL_PLATFORM = "PLATFORM"
COL_LIVE     = "IS_CURRENTLY_LIVE_ON_SITE"
COL_STATE    = "BOAT_LISTING_STATE"

ACTIONABLE_STATES = {
    "approved",
    "corrections_needed",
    "pending_review",
    "survey_received",
}

CHURN_STATES = {
    "blocked",
    "boatbound_denied",
    "deactivated",
    "deleted",
    "incomplete",
    "insurance_denied",
    "pending_insurance",
    "pending_survey",
}


def _find_col(headers: list[str], name: str) -> int:
    """Case-insensitive column index lookup. Returns -1 if not found."""
    name_upper = name.upper()
    for i, h in enumerate(headers):
        if h.strip().upper() == name_upper:
            return i
    return -1


def _is_live(val) -> bool:
    return str(val).strip() in ("1", "True", "true", "TRUE")


def _get_or_create_ws(ss, title: str, rows: int, cols: int):
    try:
        return ss.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return ss.add_worksheet(title=title, rows=rows, cols=cols)


def import_and_split(
    sheet_id: str,
    raw_sheet: str = "Sheet1",
    bs_live_sheet: str = "BS - Live",
    gmb_live_sheet: str = "GMB - Live",
    bs_not_live_sheet: str = "BS - Not Live",
    bs_churn_sheet: str = "BS - Churn",
    gmb_not_live_sheet: str = "GMB - Not Live",
    dry_run: bool = False,
    on_progress=None,
) -> dict:
    """
    Reads raw_sheet and routes rows to five destination tabs.
    ⚠ Clears each destination tab before writing.

    Returns {tab_name: row_count} for each destination tab.
    """
    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    mode = "[DRY RUN] " if dry_run else ""

    credentials_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
    if not credentials_path:
        raise EnvironmentError("GOOGLE_SHEETS_CREDENTIALS_JSON must be set in .env")

    creds  = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    client = gspread.Client(auth=creds, http_client=BackOffHTTPClient)
    ss     = client.open_by_key(sheet_id)

    report(f"{mode}Reading '{raw_sheet}'...")
    raw_ws     = ss.worksheet(raw_sheet)
    all_values = raw_ws.get_all_values()

    if not all_values:
        report(f"'{raw_sheet}' is empty — nothing to import.")
        return {}

    headers   = all_values[0]
    data_rows = [r for r in all_values[1:] if any(c.strip() for c in r)]
    report(f"  {len(data_rows)} data rows found")

    # ── Locate required columns ────────────────────────────────────────────────
    platform_idx = _find_col(headers, COL_PLATFORM)
    live_idx     = _find_col(headers, COL_LIVE)
    state_idx    = _find_col(headers, COL_STATE)

    missing = []
    if platform_idx < 0:
        missing.append(COL_PLATFORM)
    if live_idx < 0:
        missing.append(COL_LIVE)
    if state_idx < 0:
        missing.append(COL_STATE)
    if missing:
        raise ValueError(
            f"Required column(s) not found in '{raw_sheet}': {', '.join(missing)}.\n"
            f"First 10 headers: {headers[:10]}"
        )

    # ── Partition into buckets ─────────────────────────────────────────────────
    dest_names = [
        bs_live_sheet, gmb_live_sheet,
        bs_not_live_sheet, bs_churn_sheet, gmb_not_live_sheet,
    ]
    buckets: dict[str, list] = {name: [] for name in dest_names}
    unrouted: list[tuple] = []

    for row in data_rows:
        platform = (row[platform_idx] if platform_idx < len(row) else "").strip().lower()
        live     = _is_live(row[live_idx] if live_idx < len(row) else "")
        state    = (row[state_idx] if state_idx < len(row) else "").strip().lower()

        if platform == "marketplace":
            if live:
                buckets[bs_live_sheet].append(row)
            elif state in ACTIONABLE_STATES:
                buckets[bs_not_live_sheet].append(row)
            elif state in CHURN_STATES:
                buckets[bs_churn_sheet].append(row)
            else:
                unrouted.append((platform, live, state))
        elif platform == "gmb":
            if live:
                buckets[gmb_live_sheet].append(row)
            else:
                buckets[gmb_not_live_sheet].append(row)
        else:
            unrouted.append((platform, live, state))

    report("\nRouting preview:")
    for tab, rows in buckets.items():
        report(f"  {tab:<22} : {len(rows):>5} rows")
    if unrouted:
        report(f"  Unrouted               : {len(unrouted):>5} rows (unknown platform or state — review manually)")
        for plat, live, state in unrouted[:5]:
            report(f"    platform={plat!r}, live={live}, state={state!r}")
        if len(unrouted) > 5:
            report(f"    ... and {len(unrouted) - 5} more")

    if dry_run:
        report(f"\n[DRY RUN] Would clear and rewrite {len(dest_names)} tabs.")
        return {tab: len(rows) for tab, rows in buckets.items()}

    # ── Write to destination tabs ──────────────────────────────────────────────
    for tab_name, rows in buckets.items():
        report(f"\nClearing and rewriting '{tab_name}'...")
        ws = _get_or_create_ws(ss, tab_name, max(len(rows) + 100, 300), len(headers))
        ws.clear()
        if rows:
            ws.update([headers] + rows, value_input_option="RAW")
        else:
            ws.update([headers], value_input_option="RAW")
        report(f"  → {len(rows)} rows written")

    if unrouted:
        report(f"\n⚠ {len(unrouted)} rows were not routed — check platform/state values.")

    report("\nDone. Run Funnel Prep next.")
    return {tab: len(rows) for tab, rows in buckets.items()}
