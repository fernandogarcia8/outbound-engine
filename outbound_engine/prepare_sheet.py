"""
Prepares a freshly imported prospect sheet in Google Sheets by adding
required outreach tracking columns and filling in default values.

Idempotent — only fills blank cells, never overwrites existing values.
Safe to run multiple times.

Usage:
    python prepare_sheet.py --sheet-id <id> --sheet-name "Sheet1"
    python prepare_sheet.py --sheet-id <id> --sheet-name "Sheet1" --dry-run
"""

import argparse

from config import (
    COL_ACTION,
    COL_CONTACT_STATUS,
    COL_REPLIED,
    COL_EMAIL_1,
    COL_SMS_1,
    COL_EMAIL_2,
    COL_SMS_2,
    COL_EMAIL_3,
    COL_SMS_3,
    COL_NOTES,
    COL_KUSTOMER_ID,
    COL_KUSTOMER_LINK,
    SEGMENT_ACTIONS,
    GMB_LISTING_BASE_URL,
    COL_GMB_BOAT_ID,
    COL_BOAT_ADMIN_URL,
)
from sheets_connector import SheetsConnector

# Columns that need a default value written for every data row
DEFAULTS_TO_FILL = {
    COL_CONTACT_STATUS: "Pending Outreach",
    COL_ACTION:         SEGMENT_ACTIONS["prospect"],  # "Prospect"
}

# Columns that need a header added but no default value
HEADER_ONLY_COLUMNS = [
    COL_REPLIED,
    COL_EMAIL_1, COL_SMS_1,
    COL_EMAIL_2, COL_SMS_2,
    COL_EMAIL_3, COL_SMS_3,
    COL_KUSTOMER_ID,
    COL_KUSTOMER_LINK,
]

# Dropdown options and background colors (RGB 0.0–1.0) for each column.
# Values must match exactly what the engine writes — cross-ref with config.py.
DROPDOWN_CONFIG = {
    COL_ACTION: [
        ("Cross-List",   (0.529, 0.808, 0.922)),  # sky blue
        ("Skip",         (0.812, 0.847, 0.863)),  # blue-gray
        ("Manual Check", (1.000, 0.800, 0.502)),  # peach
    ],
    COL_CONTACT_STATUS: [
        ("Pending Outreach",      (1.000, 0.945, 0.463)),  # yellow
        ("Contacted",             (0.565, 0.792, 0.976)),  # light blue
        ("Interested",            (0.784, 0.902, 0.788)),  # light green
        ("Cross-list WIP",        (0.698, 0.922, 0.949)),  # light teal
        ("Not interested",        (1.000, 0.804, 0.824)),  # light pink
        ("Win",                   (0.400, 0.733, 0.416)),  # green
        ("Dual Presence",         (0.812, 0.847, 0.863)),  # blue-gray
        ("Possible Dual Presence",(1.000, 0.800, 0.502)),  # peach
    ],
}


def prepare_sheet(sheet_id: str, sheet_name: str, dry_run: bool = False) -> None:
    mode = "[DRY RUN] " if dry_run else ""
    print(f"{mode}Connecting to sheet '{sheet_name}'...")

    sheets = SheetsConnector(sheet_id, sheet_name)

    print(f"Ensuring tracking columns exist in header row...")
    if not dry_run:
        sheets.ensure_columns(HEADER_ONLY_COLUMNS)
        sheets.ensure_column_after(COL_CONTACT_STATUS, COL_NOTES)
    else:
        print(f"  → Would add (if missing): {', '.join(HEADER_ONLY_COLUMNS)}")
        print(f"  → Would insert '{COL_NOTES}' after '{COL_CONTACT_STATUS}'")

    print(f"Filling default values for blank rows...")
    rows_updated = sheets.fill_defaults(DEFAULTS_TO_FILL, dry_run=dry_run)

    print(f"Computing GMB listing URLs from {COL_GMB_BOAT_ID}...")
    rows_with_url = sheets.fill_computed_column(
        source_col=COL_GMB_BOAT_ID,
        target_col=COL_BOAT_ADMIN_URL,
        compute_fn=lambda boat_id: f"{GMB_LISTING_BASE_URL}{boat_id}",
        dry_run=dry_run,
    )

    if dry_run:
        print(f"\n[DRY RUN] Would fill defaults in {rows_updated} rows.")
        if rows_with_url:
            print(f"[DRY RUN] Would fill {COL_BOAT_ADMIN_URL} for {rows_with_url} rows.")
    else:
        print(f"\nDone. Filled defaults in {rows_updated} rows.")
        if rows_with_url:
            print(f"Filled {COL_BOAT_ADMIN_URL} for {rows_with_url} rows.")

    print(f"  → {COL_CONTACT_STATUS} = 'Pending Outreach'")
    print(f"  → {COL_ACTION} = '{SEGMENT_ACTIONS['prospect']}'")
    if rows_with_url:
        print(f"  → {COL_BOAT_ADMIN_URL} = '{GMB_LISTING_BASE_URL}' + {COL_GMB_BOAT_ID}")

    print(f"Applying dropdowns and colors...")
    updated_cols = sheets.apply_column_dropdowns(DROPDOWN_CONFIG, dry_run=dry_run)
    if dry_run:
        print(f"  [DRY RUN] Would apply dropdowns + colors to: {', '.join(updated_cols)}")
    else:
        print(f"  → Dropdowns + colors applied to: {', '.join(updated_cols)}")


def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a prospect sheet with outreach tracking columns. "
            "Adds missing headers and fills Contact Status / Action to take "
            "for any row that doesn't have them yet."
        )
    )
    parser.add_argument("--sheet-id",   required=True, help="Google Sheets document ID.")
    parser.add_argument("--sheet-name", required=True, help="Tab name within the spreadsheet.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing anything to the sheet.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    prepare_sheet(args.sheet_id, args.sheet_name, dry_run=args.dry_run)
