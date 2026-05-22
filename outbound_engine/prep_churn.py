"""
Prepares the BS - Churn tab for review.

Step 1 — Column setup: adds tracking columns and applies dropdowns.
Step 2 — Tier classification (deactivated rows only):
    Tier 1 — BOAT_LISTING_LAST_LIVE_ON_SITE_AT not empty AND year > 2024
    Tier 2 — deactivated with LAST_LIVE_AT empty or year <= 2024
    Unclassified — all other churn states (blocked, deleted, etc.) — left blank

Idempotent — skips rows that already have a Tier.
Rows set to Skip are never overwritten.
"""

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

COL_LISTING_STATE = "BOAT_LISTING_STATE"
COL_LAST_LIVE_AT  = "BOAT_LISTING_LAST_LIVE_ON_SITE_AT"

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

DROPDOWN_CONFIG = {
    COL_TIER: [
        ("Tier 1", (0.714, 0.882, 0.698)),  # soft green — most actionable
        ("Tier 2", (1.000, 0.945, 0.463)),  # yellow — less urgent
    ],
    COL_ACTION: [
        ("Review", (1.000, 0.922, 0.612)),  # soft yellow
        ("Skip",   (0.800, 0.800, 0.800)),  # gray
    ],
    COL_CONTACT_STATUS: [
        ("Pending Review", (1.000, 0.945, 0.463)),  # yellow
        ("Contacted",      (0.565, 0.792, 0.976)),  # light blue
        ("Interested",     (0.784, 0.902, 0.788)),  # light green
        ("Not Interested", (1.000, 0.804, 0.824)),  # light pink
        ("Win",            (0.400, 0.733, 0.416)),  # green
    ],
}


def _classify_row(state: str, last_live: str) -> str | None:
    """
    Returns "Tier 1", "Tier 2", or None (unclassified / leave blank).
    Only deactivated rows get a tier.
    """
    if state != "deactivated":
        return None
    if last_live and last_live[:4] > "2024":
        return "Tier 1"
    return "Tier 2"


def prep_churn(
    sheet_id: str,
    sheet_name: str = "BS - Churn",
    dry_run: bool = False,
    on_progress=None,
) -> dict:
    """
    Step 1: adds tracking columns, applies dropdowns.
    Step 2: classifies deactivated rows by tier and sets Action / Contact Status.

    Returns:
        {"tier1": int, "tier2": int, "unclassified": int, "already_set": int}
    """
    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    mode = "[DRY RUN] " if dry_run else ""
    report(f"{mode}Connecting to '{sheet_name}'...")
    sheets = SheetsConnector(sheet_id, sheet_name)

    # ── Step 1: Column setup ───────────────────────────────────────────────────
    report("Ensuring tracking columns exist...")
    if not dry_run:
        sheets.ensure_columns(TRACKING_COLUMNS)
        sheets.ensure_column_after(COL_CONTACT_STATUS, COL_NOTES)
        sheets.format_columns_as_date([
            COL_EMAIL_1, COL_SMS_1,
            COL_EMAIL_2, COL_SMS_2,
            COL_EMAIL_3, COL_SMS_3,
        ])
    else:
        report(f"  [DRY RUN] Would add (if missing): {', '.join(TRACKING_COLUMNS)}")
        report(f"  [DRY RUN] Would insert '{COL_NOTES}' after '{COL_CONTACT_STATUS}'")

    # ── Step 2: Classify ───────────────────────────────────────────────────────
    ws         = sheets._sheet
    all_values = ws.get_all_values()

    if not all_values:
        report("Sheet is empty — nothing to classify.")
        return {"tier1": 0, "tier2": 0, "unclassified": 0, "already_set": 0}

    headers = ws.row_values(1)
    col_idx = {h: i for i, h in enumerate(headers)}

    state_idx     = col_idx.get(COL_LISTING_STATE, -1)
    last_live_idx = col_idx.get(COL_LAST_LIVE_AT, -1)
    tier_idx      = col_idx.get(COL_TIER, -1)
    action_idx    = col_idx.get(COL_ACTION, -1)
    cs_idx        = col_idx.get(COL_CONTACT_STATUS, -1)

    if state_idx < 0:
        raise ValueError(f"Column '{COL_LISTING_STATE}' not found in '{sheet_name}'.")

    cell_updates: list[dict] = []
    counts = {"tier1": 0, "tier2": 0, "unclassified": 0, "already_set": 0}

    for i, row in enumerate(all_values[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue

        existing_action = (row[action_idx] if 0 <= action_idx < len(row) else "").strip()
        if existing_action.lower() == "skip":
            counts["already_set"] += 1
            continue

        existing_tier = (row[tier_idx] if 0 <= tier_idx < len(row) else "").strip()
        if existing_tier:
            counts["already_set"] += 1
            continue

        state     = (row[state_idx] if state_idx < len(row) else "").strip().lower()
        last_live = (row[last_live_idx] if 0 <= last_live_idx < len(row) else "").strip()

        tier = _classify_row(state, last_live)

        if tier is None:
            counts["unclassified"] += 1
            continue

        counts["tier1" if tier == "Tier 1" else "tier2"] += 1

        if tier_idx >= 0:
            cell_updates.append({
                "range":  rowcol_to_a1(i, tier_idx + 1),
                "values": [[tier]],
            })

        if not existing_action and action_idx >= 0:
            cell_updates.append({
                "range":  rowcol_to_a1(i, action_idx + 1),
                "values": [["Review"]],
            })

        existing_cs = (row[cs_idx] if 0 <= cs_idx < len(row) else "").strip()
        if not existing_cs and cs_idx >= 0:
            cell_updates.append({
                "range":  rowcol_to_a1(i, cs_idx + 1),
                "values": [["Pending Review"]],
            })

    report(f"\nClassification results:")
    report(f"  Tier 1 (deactivated, live > 2024) : {counts['tier1']}")
    report(f"  Tier 2 (deactivated, other)        : {counts['tier2']}")
    report(f"  Unclassified (other states)        : {counts['unclassified']}")
    report(f"  Skipped (already set / Skip)       : {counts['already_set']}")

    if dry_run:
        report(f"\n[DRY RUN] Would write {len(cell_updates)} cells and apply dropdowns.")
        return counts

    if cell_updates:
        report(f"\nWriting {len(cell_updates)} cells...")
        ws.batch_update(cell_updates)

    report("Applying dropdowns and colors...")
    updated_cols = sheets.apply_column_dropdowns(DROPDOWN_CONFIG)
    report(f"  → Applied to: {', '.join(updated_cols)}")

    report("\nDone. Focus on Tier 1 deactivated rows first.")
    return counts
