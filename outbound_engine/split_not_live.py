"""
Splits a "BS - Not Live" sheet into actionable vs churn rows based on
BOAT_LISTING_STATE. Actionable rows stay in place; churn rows are moved
to a "BS - Churn" tab (created if it doesn't exist).

Run once per new Snowflake export — not idempotent.

Actionable states (kept):
    approved, corrections_needed, pending_review, survey_received

Churn states (moved):
    outbound_denied, deactivated, deleted, incomplete,
    insurance_denied, pending_insurance, pending_survey

Usage:
    python split_not_live.py --sheet-id <id> [--dry-run]
    python split_not_live.py --sheet-id <id> \\
        --source-sheet "BS - Not Live" --churn-sheet "BS - Churn"
"""

import argparse
import os

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

COL_LISTING_STATE = "BOAT_LISTING_STATE"

ACTIONABLE_STATES = {
    "approved",
    "corrections_needed",
    "pending_review",
    "survey_received",
}

CHURN_STATES = {
    "boatbound_denied",
    "deactivated",
    "deleted",
    "incomplete",
    "insurance_denied",
    "pending_insurance",
    "pending_survey",
}


def _open_spreadsheet(sheet_id: str):
    credentials_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
    if not credentials_path:
        raise EnvironmentError(
            "GOOGLE_SHEETS_CREDENTIALS_JSON must be set in .env — "
            "point it to your service account JSON file."
        )
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(sheet_id)


def split_not_live(
    sheet_id: str,
    source_sheet: str = "BS - Not Live",
    churn_sheet: str = "BS - Churn",
    dry_run: bool = False,
    on_progress=None,
) -> dict:
    """
    Moves churn rows from source_sheet to churn_sheet.

    Returns a summary dict: {"kept": int, "moved": int, "unknown": int}
    """
    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    mode = "[DRY RUN] " if dry_run else ""
    report(f"{mode}Opening spreadsheet...")

    ss = _open_spreadsheet(sheet_id)
    source_ws = ss.worksheet(source_sheet)

    report(f"Reading '{source_sheet}'...")
    all_values = source_ws.get_all_values()

    if not all_values:
        report("Sheet is empty — nothing to do.")
        return {"kept": 0, "moved": 0, "unknown": 0}

    headers   = all_values[0]
    data_rows = all_values[1:]

    if COL_LISTING_STATE not in headers:
        raise ValueError(
            f"Column '{COL_LISTING_STATE}' not found in '{source_sheet}'.\n"
            f"Available columns: {headers}"
        )

    state_idx = headers.index(COL_LISTING_STATE)

    # ── Partition rows ─────────────────────────────────────────────────────────
    # churn_rows: list of (1-based sheet row number, raw row values)
    keep_count  = 0
    churn_rows  = []
    unknown_rows = []  # (sheet_row, raw_state) for anything not in either set

    for i, row in enumerate(data_rows):
        if not any(cell.strip() for cell in row):
            continue  # skip fully blank rows

        state     = (row[state_idx] if state_idx < len(row) else "").strip().lower()
        sheet_row = i + 2  # 1-based index, +1 for header

        if state in ACTIONABLE_STATES:
            keep_count += 1
        elif state in CHURN_STATES:
            churn_rows.append((sheet_row, row))
        else:
            unknown_rows.append((sheet_row, state))

    report(f"\nPartition results for '{source_sheet}':")
    report(f"  Actionable (keep) : {keep_count}")
    report(f"  Churn (move)      : {len(churn_rows)}")

    if unknown_rows:
        report(f"  Unknown state     : {len(unknown_rows)} (left in place — review manually)")
        for sheet_row, state in unknown_rows:
            report(f"    Row {sheet_row}: '{state}'")

    if not churn_rows:
        report("\nNo churn rows found — nothing to move.")
        return {"kept": keep_count, "moved": 0, "unknown": len(unknown_rows)}

    # ── Dry-run preview ────────────────────────────────────────────────────────
    if dry_run:
        report(f"\n[DRY RUN] Would create/open tab '{churn_sheet}'")
        report(f"[DRY RUN] Would append {len(churn_rows)} rows to '{churn_sheet}'")
        report(f"[DRY RUN] Would delete {len(churn_rows)} rows from '{source_sheet}'")
        preview = churn_rows[:5]
        for sheet_row, row in preview:
            state = row[state_idx] if state_idx < len(row) else ""
            report(f"  Row {sheet_row}: {COL_LISTING_STATE}={state}")
        if len(churn_rows) > 5:
            report(f"  ... and {len(churn_rows) - 5} more")
        return {"kept": keep_count, "moved": len(churn_rows), "unknown": len(unknown_rows)}

    # ── Ensure churn tab exists ────────────────────────────────────────────────
    existing_titles = [ws.title for ws in ss.worksheets()]
    if churn_sheet not in existing_titles:
        report(f"\nCreating tab '{churn_sheet}'...")
        churn_ws = ss.add_worksheet(
            title=churn_sheet,
            rows=max(len(churn_rows) + 50, 200),
            cols=len(headers),
        )
        churn_ws.append_row(headers, value_input_option="RAW")
    else:
        report(f"\nTab '{churn_sheet}' already exists — appending to it.")
        churn_ws = ss.worksheet(churn_sheet)

    # ── Append churn rows to destination ──────────────────────────────────────
    report(f"Appending {len(churn_rows)} rows to '{churn_sheet}'...")
    churn_ws.append_rows(
        [row for _, row in churn_rows],
        value_input_option="RAW",
    )

    # ── Delete churn rows from source (reverse order so indices stay valid) ───
    report(f"Deleting {len(churn_rows)} rows from '{source_sheet}'...")

    delete_requests = [
        {
            "deleteDimension": {
                "range": {
                    "sheetId":    source_ws.id,
                    "dimension":  "ROWS",
                    "startIndex": sheet_row - 1,  # 0-based
                    "endIndex":   sheet_row,
                }
            }
        }
        for sheet_row, _ in sorted(churn_rows, key=lambda x: x[0], reverse=True)
    ]

    ss.batch_update({"requests": delete_requests})

    # ── Summary ────────────────────────────────────────────────────────────────
    report(f"\nDone.")
    report(f"  {keep_count} rows remain in '{source_sheet}'")
    report(f"  {len(churn_rows)} rows moved to '{churn_sheet}'")
    if unknown_rows:
        report(f"  {len(unknown_rows)} rows with unrecognized states left in place — review manually")

    return {"kept": keep_count, "moved": len(churn_rows), "unknown": len(unknown_rows)}


# ── CLI entry point ────────────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Split BS - Not Live rows into actionable vs churn based on "
            "BOAT_LISTING_STATE. Moves churn rows to a separate tab. "
            "Run once per new Snowflake export — not idempotent."
        )
    )
    parser.add_argument(
        "--sheet-id",
        required=True,
        help="Google Sheets document ID.",
    )
    parser.add_argument(
        "--source-sheet",
        default="BS - Not Live",
        help='Tab containing all not-live rows (default: "BS - Not Live").',
    )
    parser.add_argument(
        "--churn-sheet",
        default="BS - Churn",
        help='Tab to move churn rows into (default: "BS - Churn").',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would happen without writing anything.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    split_not_live(
        sheet_id=args.sheet_id,
        source_sheet=args.source_sheet,
        churn_sheet=args.churn_sheet,
        dry_run=args.dry_run,
    )
