"""
Seeds Tyler and Fernando as test rows into all sheet tabs so outreach test
mode can be triggered without manual row entry. Idempotent — skips any tab
where the contact already has a test row.
"""

import gspread.exceptions

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
    conn     = SheetsConnector(sheet_id, bs_live)
    existing = conn.get_all_rows()
    added    = 0
    for m in TEAM_MEMBERS:
        if _already_seeded(existing, COL_OWNER_EMAIL, m["email"]):
            report(f"  {m['first_name']} already present — skipped")
            continue
        row = {
            COL_FIRST_NAME:     m["first_name"],
            COL_LAST_NAME:      m["last_name"],
            COL_OWNER_EMAIL:    m["email"],
            COL_OWNER_PHONE:    m["phone"],
            COL_ACTION:         "Cross-List",
            COL_CONTACT_STATUS: "Pending Outreach",
            COL_NOTES:          "test",
        }
        if not dry_run:
            conn.append_row(row)
        report(f"  {'Would add' if dry_run else 'Added'} {m['first_name']} {m['last_name']}")
        added += 1
    results["bs_live"] = added

    # ── GMB - Live ─────────────────────────────────────────────────────────────
    report(f"{mode}GMB - Live...")
    conn     = SheetsConnector(sheet_id, gmb_live)
    existing = conn.get_all_rows()
    added    = 0
    for m in TEAM_MEMBERS:
        if _already_seeded(existing, COL_OWNER_EMAIL, m["email"]):
            report(f"  {m['first_name']} already present — skipped")
            continue
        row = {
            COL_FIRST_NAME:     m["first_name"],
            COL_LAST_NAME:      m["last_name"],
            COL_OWNER_EMAIL:    m["email"],
            COL_OWNER_PHONE:    m["phone"],
            COL_ACTION:         "Cross-List",
            COL_CONTACT_STATUS: "Pending Outreach",
            COL_NOTES:          "test",
        }
        if not dry_run:
            conn.append_row(row)
        report(f"  {'Would add' if dry_run else 'Added'} {m['first_name']} {m['last_name']}")
        added += 1
    results["gmb_live"] = added

    # ── BS - Not Live ──────────────────────────────────────────────────────────
    # Tyler → Reactivate, Fernando → Get Live (tests both message variants)
    report(f"{mode}BS - Not Live...")
    conn     = SheetsConnector(sheet_id, bs_not_live)
    existing = conn.get_all_rows()
    added    = 0
    actions  = ["Reactivate", "Get Live"]
    for m, action in zip(TEAM_MEMBERS, actions):
        if _already_seeded(existing, COL_OWNER_EMAIL, m["email"]):
            report(f"  {m['first_name']} already present — skipped")
            continue
        row = {
            COL_FIRST_NAME:     m["first_name"],
            COL_LAST_NAME:      m["last_name"],
            COL_OWNER_EMAIL:    m["email"],
            COL_OWNER_PHONE:    m["phone"],
            COL_ACTION:         action,
            COL_CONTACT_STATUS: "Pending Outreach",
            COL_NOTES:          "test",
        }
        if not dry_run:
            conn.append_row(row)
        report(f"  {'Would add' if dry_run else 'Added'} {m['first_name']} {m['last_name']} ({action})")
        added += 1
    results["bs_not_live"] = added

    # ── Prospects ──────────────────────────────────────────────────────────────
    report(f"{mode}Prospects...")
    overrides = SEGMENT_COLUMN_OVERRIDES.get("prospect", {})
    email_col = overrides.get("email",      COL_OWNER_EMAIL)
    name_col  = overrides.get("first_name", COL_FIRST_NAME)
    phone_col = overrides.get("phone",      COL_OWNER_PHONE)

    conn     = SheetsConnector(sheet_id, prospects)
    existing = conn.get_all_rows()
    added    = 0
    for m in TEAM_MEMBERS:
        if _already_seeded(existing, email_col, m["email"]):
            report(f"  {m['first_name']} already present — skipped")
            continue
        row = {
            name_col:           f"{m['first_name']} {m['last_name']}",
            email_col:          m["email"],
            phone_col:          m["phone"],
            "Type":             "charter",
            COL_ACTION:         "Prospect",
            COL_NOTES:          "test",
        }
        if not dry_run:
            conn.append_row(row)
        report(f"  {'Would add' if dry_run else 'Added'} {m['first_name']} {m['last_name']}")
        added += 1
    results["prospects"] = added

    total = sum(results.values())
    report(f"\n{mode}Done — {total} row(s) added across all tabs")
    return results
