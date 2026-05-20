"""
Prepares the Prospects tab for Phase 3 outreach.

Step 1 — Column setup: adds tracking columns and applies dropdowns.
Step 2 — Funnel detection: cross-checks each prospect against BS/GMB tabs
          and Kustomer, then tags each row with a Funnel Status.

Both steps are idempotent. Safe to run after Phases 1 and 2 are complete.
"""

import re
import time

import gspread.exceptions

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
    COL_OWNER_EMAIL,
    COL_OWNER_PHONE,
    COL_DRAFT_SUBJECT,
    COL_DRAFT_EMAIL,
    COL_DRAFT_SMS,
    SEGMENT_COLUMN_OVERRIDES,
)
from kustomer_client import KustomerClient
from sheets_connector import SheetsConnector

# Prospect sheet uses different column names than Snowflake-sourced sheets
_PROSPECT_OVERRIDES = SEGMENT_COLUMN_OVERRIDES.get("prospect", {})
PROSPECT_EMAIL_COL  = _PROSPECT_OVERRIDES.get("email",      "Email")
PROSPECT_PHONE_COL  = _PROSPECT_OVERRIDES.get("phone",      "Phone Number")

# Funnel detection result column (written back to Prospects tab)
COL_FUNNEL_STATUS = "Funnel Status"

TRACKING_COLUMNS = [
    COL_FUNNEL_STATUS,
    COL_ACTION,
    COL_CONTACT_STATUS,
    COL_REPLIED,
    COL_DRAFT_SUBJECT,
    COL_DRAFT_EMAIL,
    COL_DRAFT_SMS,
    COL_EMAIL_1, COL_SMS_1,
    COL_EMAIL_2, COL_SMS_2,
    COL_EMAIL_3, COL_SMS_3,
    COL_KUSTOMER_ID,
    COL_KUSTOMER_LINK,
]

DROPDOWN_CONFIG = {
    COL_ACTION: [
        ("Prospect",     (0.714, 0.882, 0.698)),  # soft green
        ("Manual Check", (1.000, 0.800, 0.502)),  # peach
        ("Skip",         (0.800, 0.800, 0.800)),  # gray
    ],
    COL_CONTACT_STATUS: [
        ("Pending Outreach", (1.000, 0.945, 0.463)),  # yellow
        ("Contacted",        (0.565, 0.792, 0.976)),  # light blue
        ("Interested",       (0.784, 0.902, 0.788)),  # light green
        ("Not Interested",   (1.000, 0.804, 0.824)),  # light pink
        ("Win",              (0.400, 0.733, 0.416)),  # green
    ],
    COL_FUNNEL_STATUS: [
        ("Net New",     (0.714, 0.882, 0.698)),  # soft green
        ("BS Active",   (0.565, 0.792, 0.976)),  # light blue
        ("GMB Active",  (0.827, 0.706, 0.941)),  # light purple
        ("BS Funnel",   (1.000, 0.945, 0.463)),  # yellow
        ("In Kustomer", (1.000, 0.800, 0.502)),  # peach
    ],
}


# ── Normalization helpers ──────────────────────────────────────────────────────

def _norm_email(email) -> str:
    return (str(email) if email is not None else "").lower().strip().replace(" ", "")


def _norm_phone(phone) -> str:
    digits = re.sub(r"\D", "", str(phone) if phone is not None else "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def _build_lookup_maps(rows: list[dict]) -> tuple[dict, dict]:
    """Builds normalized {email: row} and {phone: row} maps from Snowflake-sourced rows."""
    by_email: dict[str, dict] = {}
    by_phone: dict[str, dict] = {}
    for r in rows:
        ne = _norm_email(r.get(COL_OWNER_EMAIL, ""))
        np = _norm_phone(r.get(COL_OWNER_PHONE, ""))
        if ne:
            by_email[ne] = r
        if np:
            by_phone[np] = r
    by_email.pop("", None)
    by_phone.pop("", None)
    return by_email, by_phone


def _safe_read(spreadsheet_id: str, sheet_name: str, report) -> list[dict]:
    try:
        rows = SheetsConnector(spreadsheet_id, sheet_name).get_all_rows()
        report(f"  {len(rows)} rows in '{sheet_name}'")
        return rows
    except gspread.exceptions.WorksheetNotFound:
        report(f"  '{sheet_name}' not found — skipping")
        return []


# ── Main ───────────────────────────────────────────────────────────────────────

def prep_prospects(
    sheet_id: str,
    sheet_name: str = "Prospects",
    bs_live_sheet: str = "BS - Live",
    gmb_live_sheet: str = "GMB - Live",
    bs_not_live_sheet: str = "BS - Not Live",
    bs_churn_sheet: str = "BS - Churn",
    dry_run: bool = False,
    on_progress=None,
) -> dict:
    """
    Step 1: ensures tracking columns exist, sets defaults, applies dropdowns.
    Step 2: cross-checks each prospect against all funnel tabs + Kustomer and
            writes a Funnel Status back to the sheet.

    Returns {"filled": int, "already_set": int, "net_new": int, "matched": int}
    """
    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    mode = "[DRY RUN] " if dry_run else ""

    # ── Step 1: Column setup ───────────────────────────────────────────────────
    report(f"{mode}Connecting to '{sheet_name}'...")
    sheets = SheetsConnector(sheet_id, sheet_name)

    report("Ensuring tracking columns exist...")
    if not dry_run:
        sheets.ensure_columns(TRACKING_COLUMNS)
        sheets.ensure_column_after(COL_CONTACT_STATUS, COL_NOTES)
    else:
        report(f"  [DRY RUN] Would add (if missing): {', '.join(TRACKING_COLUMNS)}")
        report(f"  [DRY RUN] Would insert '{COL_NOTES}' after '{COL_CONTACT_STATUS}'")

    # Count rows already classified before we fill defaults (for accurate reporting)
    all_values = sheets._sheet.get_all_values()
    headers    = all_values[0] if all_values else []
    action_idx = headers.index(COL_ACTION) if COL_ACTION in headers else -1
    already_set = sum(
        1 for row in all_values[1:]
        if any(c.strip() for c in row)
        and action_idx >= 0
        and action_idx < len(row)
        and row[action_idx].strip()
    )

    report("Setting Action to take and Contact Status for new rows...")
    filled = sheets.fill_defaults(
        {
            COL_ACTION:         "Prospect",
            COL_CONTACT_STATUS: "Pending Outreach",
        },
        dry_run=dry_run,
    )
    report(f"  {filled} rows updated · {already_set} already had values (skipped)")

    # ── Step 2: Funnel detection ───────────────────────────────────────────────
    report(f"\n{mode}Step 2 — Funnel detection")
    report("Reading reference sheets...")
    bs_live_rows     = _safe_read(sheet_id, bs_live_sheet,    report)
    gmb_live_rows    = _safe_read(sheet_id, gmb_live_sheet,   report)
    bs_not_live_rows = _safe_read(sheet_id, bs_not_live_sheet, report)
    bs_churn_rows    = _safe_read(sheet_id, bs_churn_sheet,   report)

    bs_live_by_email,     bs_live_by_phone     = _build_lookup_maps(bs_live_rows)
    gmb_live_by_email,    gmb_live_by_phone    = _build_lookup_maps(gmb_live_rows)
    bs_not_live_by_email, bs_not_live_by_phone = _build_lookup_maps(bs_not_live_rows)
    bs_churn_by_email,    bs_churn_by_phone    = _build_lookup_maps(bs_churn_rows)

    report("\nReading Prospects rows...")
    prospect_rows = sheets.get_all_rows()
    report(f"  {len(prospect_rows)} rows to check")

    kustomer = None if dry_run else KustomerClient()

    # Separate update buckets so batch_update_rows can match on the right column
    email_updates: dict[str, dict] = {}
    phone_updates: dict[str, dict] = {}  # rows with no email

    net_new_count = 0
    matched_count = 0

    report(f"\n{mode}Checking each prospect against funnel tabs + Kustomer...")
    for i, row in enumerate(prospect_rows, start=1):
        p_email = str(row.get(PROSPECT_EMAIL_COL) or "").strip()
        p_phone = str(row.get(PROSPECT_PHONE_COL) or "").strip()
        ne      = _norm_email(p_email)
        np      = _norm_phone(p_phone)
        display = p_email or p_phone

        if not ne and not np:
            continue  # no contact info — nothing to check

        funnel_status = None
        note          = ""

        # L1+2: BS - Live
        if (ne and ne in bs_live_by_email) or (np and np in bs_live_by_phone):
            funnel_status = "BS Active"
            note          = "Found in BS - Live"

        # L3+4: GMB - Live
        elif (ne and ne in gmb_live_by_email) or (np and np in gmb_live_by_phone):
            funnel_status = "GMB Active"
            note          = "Found in GMB - Live"

        # L5+6: BS - Not Live
        elif (ne and ne in bs_not_live_by_email) or (np and np in bs_not_live_by_phone):
            matched = bs_not_live_by_email.get(ne) or bs_not_live_by_phone.get(np)
            state   = str(matched.get("BOAT_LISTING_STATE") or "").strip()
            funnel_status = "BS Funnel"
            note          = f"BS - Not Live: {state}" if state else "BS - Not Live"

        # L7+8: BS - Churn
        elif (ne and ne in bs_churn_by_email) or (np and np in bs_churn_by_phone):
            matched = bs_churn_by_email.get(ne) or bs_churn_by_phone.get(np)
            state   = str(matched.get("BOAT_LISTING_STATE") or "").strip()
            funnel_status = "BS Funnel"
            note          = f"BS - Churn: {state}" if state else "BS - Churn"

        # L9: Kustomer API lookup
        else:
            found_in_kustomer = False
            if not dry_run:
                try:
                    if ne:
                        customer = kustomer.get_customer_by_email(p_email)
                        if customer:
                            found_in_kustomer = True
                    if not found_in_kustomer and np:
                        customer = kustomer.get_customer_by_phone(p_phone)
                        if customer:
                            found_in_kustomer = True
                except Exception as exc:
                    report(f"  [{i}] Kustomer lookup failed for {display}: {exc}")
                time.sleep(0.3)
            else:
                report(f"  [{i}/{len(prospect_rows)}] Would look up '{display}' in Kustomer")

            if found_in_kustomer:
                funnel_status = "In Kustomer"
                note          = "Found in Kustomer — verify before outreach"
            else:
                funnel_status = "Net New"

        # Build the sheet update for this row
        if funnel_status == "Net New":
            _upd = {COL_FUNNEL_STATUS: "Net New"}
            net_new_count += 1
        else:
            current_action = str(row.get(COL_ACTION) or "").strip()
            _upd = {
                COL_FUNNEL_STATUS: funnel_status,
                COL_NOTES:         note,
            }
            # Flip to Manual Check unless the user already set Skip deliberately
            if current_action != "Skip":
                _upd[COL_ACTION] = "Manual Check"
            matched_count += 1
            report(f"  [{i}/{len(prospect_rows)}] {display} → {funnel_status} ({note})")

        if p_email:
            email_updates[p_email] = _upd
        else:
            phone_updates[p_phone] = _upd

    # ── Apply dropdowns ────────────────────────────────────────────────────────
    report("\nApplying dropdowns and colors...")
    if not dry_run:
        updated_cols = sheets.apply_column_dropdowns(DROPDOWN_CONFIG)
        report(f"  -> Applied to: {', '.join(updated_cols)}")
    else:
        report(f"  [DRY RUN] Would apply dropdowns to: {', '.join(DROPDOWN_CONFIG.keys())}")

    # ── Write detection results ────────────────────────────────────────────────
    if not dry_run and (email_updates or phone_updates):
        report("Writing funnel detection results...")
        written = 0
        if email_updates:
            written += sheets.batch_update_rows(PROSPECT_EMAIL_COL, email_updates)
        if phone_updates:
            written += sheets.batch_update_rows(PROSPECT_PHONE_COL, phone_updates)
        report(f"  {written} rows tagged")
    elif dry_run:
        report(f"\n[DRY RUN] Would tag:")
        report(f"  {net_new_count} rows → Net New (clear to contact)")
        report(f"  {matched_count} rows → already in funnel (Manual Check)")

    report(f"\nDone.")
    report(f"  {net_new_count} net new prospects — clear to contact")
    report(f"  {matched_count} already in funnel — set to Manual Check, review before outreach")

    return {
        "filled":     filled,
        "already_set": already_set,
        "net_new":    net_new_count,
        "matched":    matched_count,
    }
