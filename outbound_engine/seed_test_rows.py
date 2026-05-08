"""
Seeds Tyler and Fernando as test rows into all sheet tabs so outreach test
mode can be triggered without manual row entry. Idempotent — skips any tab
where the contact already has a test row. Skips tabs that don't exist yet.
"""

from gspread.exceptions import WorksheetNotFound

from config import (
    TEAM_MEMBERS,
    COL_OWNER_EMAIL,
    COL_OWNER_PHONE,
    COL_FIRST_NAME,
    COL_LAST_NAME,
    COL_ACTION,
    COL_CONTACT_STATUS,
    COL_NOTES,
    SEGMENT_COLUMN_OVERRIDES,
)
from sheets_connector import SheetsConnector


def _already_seeded(rows: list[dict], email_col: str, email: str) -> bool:
    for row in rows:
        if (str(row.get(email_col, "")).strip().lower() == email.lower()
                and str(row.get(COL_NOTES, "")).strip().lower() == "test"):
            return True
    return False


def _seed_tab(sheet_id, tab_name, rows_fn, dry_run, report):
    """
    Opens tab_name, calls rows_fn(conn, existing) to get the list of row dicts
    to append, writes them, and returns the count added. Skips missing tabs.
    """
    try:
        conn = SheetsConnector(sheet_id, tab_name)
    except WorksheetNotFound:
        report(f"  Tab '{tab_name}' not found — skipped")
        return 0

    existing = conn.get_all_rows()
    rows     = rows_fn(existing)
    added    = 0
    for row, label in rows:
        if not dry_run:
            conn.append_row(row)
        report(f"  {'Would add' if dry_run else 'Added'} {label}")
        added += 1
    return added


def seed_test_rows(
    sheet_id: str,
    bs_live: str      = "BS - Live",
    gmb_live: str     = "GMB - Live",
    bs_not_live: str  = "BS - Not Live",
    prospects: str    = "Prospects",
    dry_run: bool     = False,
    on_progress       = None,
) -> dict:
    """
    Adds test rows to each tab. Returns {tab: rows_added}.

    BS - Not Live: Tyler → Reactivate, Fernando → Get Live.
    All other tabs: both → Cross-List (Live) or Prospect.
    """
    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    mode    = "[DRY RUN] " if dry_run else ""
    results = {}

    # ── BS - Live ──────────────────────────────────────────────────────────────
    report(f"{mode}BS - Live...")
    def _bs_live_rows(existing):
        rows = []
        for m in TEAM_MEMBERS:
            if _already_seeded(existing, COL_OWNER_EMAIL, m["email"]):
                report(f"  {m['first_name']} already present — skipped")
                continue
            rows.append(({
                COL_FIRST_NAME:     m["first_name"],
                COL_LAST_NAME:      m["last_name"],
                COL_OWNER_EMAIL:    m["email"],
                COL_OWNER_PHONE:    m["phone"],
                COL_ACTION:         "Cross-List",
                COL_CONTACT_STATUS: "Pending Outreach",
                COL_NOTES:          "test",
            }, f"{m['first_name']} {m['last_name']}"))
        return rows
    results["bs_live"] = _seed_tab(sheet_id, bs_live, _bs_live_rows, dry_run, report)

    # ── GMB - Live ─────────────────────────────────────────────────────────────
    report(f"{mode}GMB - Live...")
    def _gmb_live_rows(existing):
        rows = []
        for m in TEAM_MEMBERS:
            if _already_seeded(existing, COL_OWNER_EMAIL, m["email"]):
                report(f"  {m['first_name']} already present — skipped")
                continue
            rows.append(({
                COL_FIRST_NAME:     m["first_name"],
                COL_LAST_NAME:      m["last_name"],
                COL_OWNER_EMAIL:    m["email"],
                COL_OWNER_PHONE:    m["phone"],
                COL_ACTION:         "Cross-List",
                COL_CONTACT_STATUS: "Pending Outreach",
                COL_NOTES:          "test",
            }, f"{m['first_name']} {m['last_name']}"))
        return rows
    results["gmb_live"] = _seed_tab(sheet_id, gmb_live, _gmb_live_rows, dry_run, report)

    # ── BS - Not Live ──────────────────────────────────────────────────────────
    # Tyler → Reactivate, Fernando → Get Live (tests both message variants)
    report(f"{mode}BS - Not Live...")
    def _bs_not_live_rows(existing):
        rows    = []
        actions = ["Reactivate", "Get Live"]
        for m, action in zip(TEAM_MEMBERS, actions):
            if _already_seeded(existing, COL_OWNER_EMAIL, m["email"]):
                report(f"  {m['first_name']} already present — skipped")
                continue
            rows.append(({
                COL_FIRST_NAME:     m["first_name"],
                COL_LAST_NAME:      m["last_name"],
                COL_OWNER_EMAIL:    m["email"],
                COL_OWNER_PHONE:    m["phone"],
                COL_ACTION:         action,
                COL_CONTACT_STATUS: "Pending Outreach",
                COL_NOTES:          "test",
            }, f"{m['first_name']} {m['last_name']} ({action})"))
        return rows
    results["bs_not_live"] = _seed_tab(sheet_id, bs_not_live, _bs_not_live_rows, dry_run, report)

    # ── Prospects ──────────────────────────────────────────────────────────────
    report(f"{mode}Prospects...")
    overrides = SEGMENT_COLUMN_OVERRIDES.get("prospect", {})
    email_col = overrides.get("email",      COL_OWNER_EMAIL)
    name_col  = overrides.get("first_name", COL_FIRST_NAME)
    phone_col = overrides.get("phone",      COL_OWNER_PHONE)

    def _prospect_rows(existing):
        rows = []
        for m in TEAM_MEMBERS:
            if _already_seeded(existing, email_col, m["email"]):
                report(f"  {m['first_name']} already present — skipped")
                continue
            rows.append(({
                name_col:           f"{m['first_name']} {m['last_name']}",
                email_col:          m["email"],
                phone_col:          m["phone"],
                "Type":             "charter",
                COL_ACTION:         "Prospect",
                COL_NOTES:          "test",
            }, f"{m['first_name']} {m['last_name']}"))
        return rows
    results["prospects"] = _seed_tab(sheet_id, prospects, _prospect_rows, dry_run, report)

    total = sum(results.values())
    report(f"\n{mode}Done — {total} row(s) added across all tabs")
    return results
