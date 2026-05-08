"""
Classifies rows in "BS - Not Live" by tier and writes Tier, Action to take,
and Contact Status back to the sheet. Also ensures all tracking columns exist
and applies BS - Not Live-specific dropdowns.

Run after split_not_live.py. Idempotent — skips rows that already have a Tier.

Tier logic:
  Tier 1  — BOAT_LISTING_STATE = approved
              LAST_LIVE_ON_SITE_AT empty   → Action: Reactivate
              LAST_LIVE_ON_SITE_AT present → Action: Get Live
  Tier 2  — pending_review or survey_received, created >= 2023-01-01 → Get Live
  Tier 3  — pending_review or survey_received, created  < 2023-01-01 → Get Live
  Rehab   — corrections_needed → Action: Check, Status: Needs Review

Usage:
    python classify_not_live.py --sheet-id <id> [--dry-run]
    python classify_not_live.py --sheet-id <id> --sheet-name "BS - Not Live"
"""

import argparse

from gspread.utils import rowcol_to_a1

from config import (
    COL_ACTION,
    COL_CONTACT_STATUS,
    COL_NOTES,
    COL_REPLIED,
    COL_EMAIL_1, COL_SMS_1,
    COL_EMAIL_2, COL_SMS_2,
    COL_EMAIL_3, COL_SMS_3,
    COL_KUSTOMER_ID,
    COL_KUSTOMER_LINK,
    COL_TIER,
)
from sheets_connector import SheetsConnector

# ── Snowflake column names ─────────────────────────────────────────────────────
COL_LISTING_STATE   = "BOAT_LISTING_STATE"
COL_CREATED_AT      = "BOAT_LISTING_CREATED_AT"
COL_LAST_LIVE_AT    = "BOAT_LISTING_LAST_LIVE_ON_SITE_AT"

TIER2_CUTOFF = "2023-01-01"  # YYYY-MM-DD

# ── Tracking columns added to BS - Not Live ────────────────────────────────────
# Order matters — these are appended left-to-right if missing.
# Notes is inserted positionally after Contact Status via ensure_column_after.
TRACKING_COLUMNS = [
    COL_TIER,
    COL_ACTION,
    COL_CONTACT_STATUS,
    COL_REPLIED,
    COL_EMAIL_1, COL_SMS_1,
    COL_EMAIL_2, COL_SMS_2,
    COL_EMAIL_3, COL_SMS_3,
    COL_KUSTOMER_ID,
    COL_KUSTOMER_LINK,
]

# ── Dropdown config for BS - Not Live (different from Live sheets) ─────────────
DROPDOWN_CONFIG = {
    COL_ACTION: [
        ("Reactivate", (0.671, 0.851, 0.914)),  # soft blue
        ("Get Live",   (0.714, 0.882, 0.698)),  # soft green
        ("Check",      (1.000, 0.800, 0.502)),  # peach
    ],
    COL_CONTACT_STATUS: [
        ("Pending Outreach", (1.000, 0.945, 0.463)),  # yellow
        ("Contacted",        (0.565, 0.792, 0.976)),  # light blue
        ("Interested",       (0.784, 0.902, 0.788)),  # light green
        ("Not interested",   (1.000, 0.804, 0.824)),  # light pink
        ("Win",              (0.400, 0.733, 0.416)),  # green
        ("Needs Review",     (1.000, 0.800, 0.502)),  # peach
    ],
}


# ── Classification logic ───────────────────────────────────────────────────────

def _classify_row(row: list, col_idx: dict) -> dict | None:
    """
    Returns {COL_TIER: ..., COL_ACTION: ..., COL_CONTACT_STATUS: ...}
    or None if the state is unrecognized.
    """
    def get(col: str) -> str:
        idx = col_idx.get(col, -1)
        return (row[idx] if 0 <= idx < len(row) else "").strip()

    state    = get(COL_LISTING_STATE).lower()
    created  = get(COL_CREATED_AT)[:10]   # YYYY-MM-DD prefix
    last_live = get(COL_LAST_LIVE_AT)

    if state == "approved":
        action = "Get Live" if not last_live else "Reactivate"
        return {COL_TIER: "Tier 1", COL_ACTION: action, COL_CONTACT_STATUS: "Pending Outreach"}

    if state in ("pending_review", "survey_received"):
        tier = "Tier 2" if created >= TIER2_CUTOFF else "Tier 3"
        return {COL_TIER: tier, COL_ACTION: "Get Live", COL_CONTACT_STATUS: "Pending Outreach"}

    if state == "corrections_needed":
        return {COL_TIER: "Rehab", COL_ACTION: "Check", COL_CONTACT_STATUS: "Needs Review"}

    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def classify_not_live(
    sheet_id: str,
    sheet_name: str = "BS - Not Live",
    dry_run: bool = False,
    on_progress=None,
) -> dict:
    """
    Classifies all unclassified rows and writes Tier / Action / Status.

    Returns {"classified": int, "skipped_already_set": int, "skipped_unknown": int}
    """
    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    mode = "[DRY RUN] " if dry_run else ""
    report(f"{mode}Connecting to '{sheet_name}'...")

    sheets = SheetsConnector(sheet_id, sheet_name)

    # ── Ensure tracking columns exist ──────────────────────────────────────────
    report("Ensuring tracking columns exist...")
    if not dry_run:
        sheets.ensure_columns(TRACKING_COLUMNS)
        sheets.ensure_column_after(COL_CONTACT_STATUS, COL_NOTES)
    else:
        report(f"  [DRY RUN] Would add (if missing): {', '.join(TRACKING_COLUMNS)}")
        report(f"  [DRY RUN] Would insert '{COL_NOTES}' after '{COL_CONTACT_STATUS}'")

    # ── Read sheet ─────────────────────────────────────────────────────────────
    report("Reading rows...")
    ws         = sheets._sheet
    all_values = ws.get_all_values()
    if not all_values:
        report("Sheet is empty — nothing to classify.")
        return {"classified": 0, "skipped_already_set": 0, "skipped_unknown": 0}

    headers = ws.row_values(1)
    col_idx = {h: i for i, h in enumerate(headers)}

    if COL_LISTING_STATE not in col_idx:
        raise ValueError(
            f"Column '{COL_LISTING_STATE}' not found in '{sheet_name}'."
        )

    tier_idx = col_idx.get(COL_TIER, -1)

    # ── Classify ───────────────────────────────────────────────────────────────
    cell_updates       = []
    classified         = 0
    skipped_already    = 0
    skipped_unknown    = 0

    for i, row in enumerate(all_values[1:], start=2):  # start=2 → 1-based sheet row
        if not any(cell.strip() for cell in row):
            continue  # blank row

        # Skip if Tier already set
        existing_tier = (row[tier_idx] if 0 <= tier_idx < len(row) else "").strip()
        if existing_tier:
            skipped_already += 1
            continue

        result = _classify_row(row, col_idx)
        if result is None:
            state = (row[col_idx.get(COL_LISTING_STATE, 0)] if col_idx.get(COL_LISTING_STATE) is not None else "")
            report(f"  Row {i}: unrecognized state '{state}' — skipping")
            skipped_unknown += 1
            continue

        classified += 1
        for col_name, value in result.items():
            # col_idx may have been updated after ensure_columns — re-fetch if needed
            if col_name not in col_idx:
                continue
            col_num = col_idx[col_name] + 1  # 1-based
            cell_updates.append({
                "range":  rowcol_to_a1(i, col_num),
                "values": [[value]],
            })

    report(f"\nClassification preview:")
    report(f"  To classify         : {classified}")
    report(f"  Already classified  : {skipped_already} (skipped)")
    report(f"  Unrecognized state  : {skipped_unknown} (skipped)")

    if dry_run:
        # 3 cells per row: Tier + Action to take + Contact Status
        report(f"\n[DRY RUN] Would write {classified * 3} cells across {classified} rows.")
        report(f"[DRY RUN] Would apply dropdowns to: {', '.join(DROPDOWN_CONFIG.keys())}")
        return {"classified": classified, "skipped_already_set": skipped_already, "skipped_unknown": skipped_unknown}

    # ── Write classifications ──────────────────────────────────────────────────
    if cell_updates:
        report(f"\nWriting {classified} row classifications...")
        ws.batch_update(cell_updates)
    else:
        report("\nNo rows to update.")

    # ── Apply dropdowns ────────────────────────────────────────────────────────
    report("Applying dropdowns and colors...")
    updated_cols = sheets.apply_column_dropdowns(DROPDOWN_CONFIG)
    report(f"  → Applied to: {', '.join(updated_cols)}")

    report(f"\nDone.")
    report(f"  {classified} rows classified")
    report(f"  {skipped_already} rows already had a Tier (left unchanged)")
    if skipped_unknown:
        report(f"  {skipped_unknown} rows with unrecognized states — review manually")

    return {"classified": classified, "skipped_already_set": skipped_already, "skipped_unknown": skipped_unknown}


# ── CLI entry point ────────────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Classify BS - Not Live rows by tier and set Action to take + "
            "Contact Status. Idempotent — skips rows already classified."
        )
    )
    parser.add_argument("--sheet-id",   required=True, help="Google Sheets document ID.")
    parser.add_argument(
        "--sheet-name",
        default="BS - Not Live",
        help='Tab name to classify (default: "BS - Not Live").',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview classifications without writing to the sheet.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    classify_not_live(
        sheet_id=args.sheet_id,
        sheet_name=args.sheet_name,
        dry_run=args.dry_run,
    )
