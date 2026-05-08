"""
Cross-platform detection script.

Compares BS Live and GMB Live tabs in the same spreadsheet and tags every
owner row with one of three statuses:

  Dual Presence          — confirmed active on both platforms (skip outreach)
  Possible Dual Presence — found in Kustomer but emails/phones don't match
                           (verify manually before contacting)
  Pending Outreach       — not found on other platform at all (contact them)

Matching runs in three layers:
  Layer 1: Normalized email  (lowercase, stripped)
  Layer 2: Normalized phone  (digits only)
  Layer 3: Kustomer lookup   (only for GMB owners not matched in layers 1-2,
                              since Kustomer is Boatsetter-only)

CLI usage:
    python cross_list.py \\
        --spreadsheet-id 1MgOCGT6c... \\
        --bs-sheet "BS - Live" \\
        --gmb-sheet "GMB - Live"

    python cross_list.py \\
        --spreadsheet-id 1MgOCGT6c... \\
        --bs-sheet "BS - Live" \\
        --gmb-sheet "GMB - Live" \\
        --dry-run
"""

import argparse
import re
import time

import gspread.exceptions

from config import (
    COL_OWNER_EMAIL,
    COL_OWNER_PHONE,
    COL_FIRST_NAME,
    COL_LAST_NAME,
    COL_ACTION,
    COL_CONTACT_STATUS,
    COL_NOTES,
    COL_REPLIED,
    COL_EMAIL_1, COL_SMS_1,
    COL_EMAIL_2, COL_SMS_2,
    COL_EMAIL_3, COL_SMS_3,
    COL_KUSTOMER_ID,
    COL_KUSTOMER_LINK,
    CROSS_LIST_STATUS,
    GMB_LISTING_BASE_URL,
    COL_GMB_BOAT_ID,
    COL_BOAT_ADMIN_URL,
    COL_GMB_LISTING_URL,
    COL_BS_ADMIN_URL,
)

# Outreach tracking columns added to both Live sheets during prep
_LIVE_TRACKING_COLUMNS = [
    COL_ACTION,
    COL_CONTACT_STATUS,
    COL_NOTES,
    COL_REPLIED,
    COL_EMAIL_1, COL_SMS_1,
    COL_EMAIL_2, COL_SMS_2,
    COL_EMAIL_3, COL_SMS_3,
    COL_KUSTOMER_ID,
    COL_KUSTOMER_LINK,
]

_LIVE_DROPDOWN_CONFIG = {
    COL_ACTION: [
        ("Cross-List",    (0.565, 0.792, 0.976)),  # light blue
        ("Skip",          (0.800, 0.800, 0.800)),  # gray
        ("Manual Check",  (1.000, 0.800, 0.502)),  # peach
    ],
    COL_CONTACT_STATUS: [
        ("Pending Outreach",    (1.000, 0.945, 0.463)),  # yellow
        ("Contacted",           (0.851, 0.851, 0.851)),  # silver
        ("Interested",          (0.784, 0.902, 0.788)),  # light green
        ("Cross-List WIP",      (0.565, 0.792, 0.976)),  # light blue
        ("Not Interested",      (1.000, 0.700, 0.700)),  # light red
        ("Win",                 (0.400, 0.733, 0.416)),  # dark green
        ("Dual Presence",       (0.800, 0.710, 0.910)),  # lavender
        ("Possible Dual Presence", (1.000, 0.850, 0.650)),  # light orange
    ],
}
from kustomer_client import KustomerClient
from sheets_connector import SheetsConnector
from logger import setup_file_logger
from datetime import datetime, timezone


# ── Normalization helpers ──────────────────────────────────────────────────────

def _norm_email(email: str) -> str:
    return (email or "").lower().strip().replace(" ", "")


def _norm_phone(phone) -> str:
    digits = re.sub(r"\D", "", str(phone) if phone is not None else "")
    # Strip leading country code (1) if 11 digits starting with 1
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def _norm_name(first: str, last: str) -> str:
    """Normalized 'first last' for name-based matching. Returns '' if either part is missing."""
    first = (first or "").strip()
    last  = (last  or "").strip()
    if not first or not last:
        return ""
    return f"{first} {last}".lower()


# ── Main detection logic ───────────────────────────────────────────────────────

def detect_cross_list(
    spreadsheet_id: str,
    bs_sheet_name: str,
    gmb_sheet_name: str,
    churn_sheet_name: str = "BS - Churn",
    not_live_sheet_name: str = "BS - Not Live",
    dry_run: bool = False,
    on_progress=None,
) -> dict:
    """
    Runs cross-platform detection and tags both sheets.

    Returns a summary dict with counts of each status assigned.
    """

    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    logger = setup_file_logger(f"cross_list_{run_timestamp}")
    mode   = "[DRY RUN] " if dry_run else ""

    report(f"{mode}Starting cross-list detection")
    report(f"  BS sheet : {bs_sheet_name}")
    report(f"  GMB sheet: {gmb_sheet_name}")

    # ── Read both sheets ───────────────────────────────────────────────────────
    report("\nReading BS Live sheet...")
    bs_connector  = SheetsConnector(spreadsheet_id, bs_sheet_name)
    bs_rows       = bs_connector.get_all_rows()
    report(f"  {len(bs_rows)} rows found in BS Live")

    report("Reading GMB Live sheet...")
    gmb_connector = SheetsConnector(spreadsheet_id, gmb_sheet_name)
    gmb_rows      = gmb_connector.get_all_rows()
    report(f"  {len(gmb_rows)} rows found in GMB Live")

    if not dry_run:
        report("\nEnsuring outreach columns and dropdowns on both Live sheets...")
        bs_connector.ensure_columns(_LIVE_TRACKING_COLUMNS + [COL_GMB_LISTING_URL])
        gmb_connector.ensure_columns(_LIVE_TRACKING_COLUMNS + [COL_BS_ADMIN_URL])
        bs_connector.apply_column_dropdowns(_LIVE_DROPDOWN_CONFIG)
        gmb_connector.apply_column_dropdowns(_LIVE_DROPDOWN_CONFIG)

    # ── Read BS - Churn and BS - Not Live for Layer 4+5 ───────────────────────
    def _read_funnel_sheet(name: str) -> list[dict]:
        try:
            rows = SheetsConnector(spreadsheet_id, name).get_all_rows()
            report(f"  {len(rows)} rows found in '{name}'")
            return rows
        except gspread.exceptions.WorksheetNotFound:
            report(f"  Tab '{name}' not found — skipping Layer check against it")
            return []

    report("\nReading funnel sheets for Layer 4+5...")
    churn_rows    = _read_funnel_sheet(churn_sheet_name)
    not_live_rows = _read_funnel_sheet(not_live_sheet_name)

    def _build_funnel_maps(rows: list[dict]) -> tuple[dict, dict, dict]:
        by_email = {_norm_email(str(r.get(COL_OWNER_EMAIL) or "")): r
                    for r in rows if r.get(COL_OWNER_EMAIL)}
        by_phone = {_norm_phone(str(r.get(COL_OWNER_PHONE) or "")): r
                    for r in rows if r.get(COL_OWNER_PHONE)}
        by_name  = {}
        for r in rows:
            nn = _norm_name(r.get(COL_FIRST_NAME, ""), r.get(COL_LAST_NAME, ""))
            if nn:
                by_name[nn] = r
        by_email.pop("", None)
        by_phone.pop("", None)
        return by_email, by_phone, by_name

    churn_by_email,    churn_by_phone,    churn_by_name    = _build_funnel_maps(churn_rows)
    not_live_by_email, not_live_by_phone, not_live_by_name = _build_funnel_maps(not_live_rows)

    # ── Build normalized lookup sets from each sheet ───────────────────────────
    bs_emails  = {_norm_email(r.get(COL_OWNER_EMAIL,  "")) for r in bs_rows if r.get(COL_OWNER_EMAIL)}
    bs_phones  = {_norm_phone(r.get(COL_OWNER_PHONE,  "")) for r in bs_rows if r.get(COL_OWNER_PHONE)}
    gmb_emails = {_norm_email(r.get(COL_OWNER_EMAIL,  "")) for r in gmb_rows if r.get(COL_OWNER_EMAIL)}
    gmb_phones = {_norm_phone(r.get(COL_OWNER_PHONE,  "")) for r in gmb_rows if r.get(COL_OWNER_PHONE)}

    # Remove empty strings from sets
    bs_emails.discard("");  bs_phones.discard("")
    gmb_emails.discard(""); gmb_phones.discard("")

    report(f"\nBS  — {len(bs_emails)} unique emails, {len(bs_phones)} unique phones")
    report(f"GMB — {len(gmb_emails)} unique emails, {len(gmb_phones)} unique phones")

    # Row lookup maps — used to pull the counterpart's admin URL for dual-presence rows
    gmb_row_by_email = {_norm_email(str(r.get(COL_OWNER_EMAIL) or "")): r for r in gmb_rows if r.get(COL_OWNER_EMAIL)}
    gmb_row_by_phone = {_norm_phone(str(r.get(COL_OWNER_PHONE) or "")): r for r in gmb_rows if r.get(COL_OWNER_PHONE)}
    bs_row_by_email  = {_norm_email(str(r.get(COL_OWNER_EMAIL) or "")): r for r in bs_rows  if r.get(COL_OWNER_EMAIL)}
    bs_row_by_phone  = {_norm_phone(str(r.get(COL_OWNER_PHONE) or "")): r for r in bs_rows  if r.get(COL_OWNER_PHONE)}
    for _d in (gmb_row_by_email, gmb_row_by_phone, bs_row_by_email, bs_row_by_phone):
        _d.pop("", None)

    # ── Layer 1+2: Match BS rows against GMB ──────────────────────────────────
    report("\n── Layer 1+2: Email + phone matching ──")

    bs_email_updates  = {}   # {email: {col: val}}
    bs_phone_updates  = {}   # {phone: {col: val}} — rows with no email
    gmb_email_updates = {}
    gmb_phone_updates = {}

    bs_dual      = 0
    bs_cross_list = 0

    for row in bs_rows:
        email = str(row.get(COL_OWNER_EMAIL) or "").strip()
        phone = str(row.get(COL_OWNER_PHONE) or "").strip()
        match_val = email or phone
        if not match_val:
            continue

        ne = _norm_email(email)
        np = _norm_phone(phone)

        if (ne and ne in gmb_emails) or (np and np in gmb_phones):
            status = CROSS_LIST_STATUS["dual"]
            action = "Skip"
            bs_dual += 1
        else:
            status = CROSS_LIST_STATUS["target"]
            action = "Cross-List"
            bs_cross_list += 1

        _upd = {COL_ACTION: action, COL_CONTACT_STATUS: status}
        if status == CROSS_LIST_STATUS["dual"]:
            matched_gmb = gmb_row_by_email.get(ne) or gmb_row_by_phone.get(np)
            if matched_gmb:
                boat_id = str(matched_gmb.get(COL_GMB_BOAT_ID) or "").strip()
                if boat_id:
                    _upd[COL_GMB_LISTING_URL] = f"{GMB_LISTING_BASE_URL}{boat_id}"

        if email:
            bs_email_updates[email] = _upd
        else:
            bs_phone_updates[phone] = _upd

    report(f"  BS results → {bs_dual} Dual Presence, {bs_cross_list} Cross-List candidates")

    # ── Layer 1+2 for GMB rows ────────────────────────────────────────────────
    gmb_dual          = 0
    gmb_possible      = 0
    gmb_cross_list    = 0
    gmb_unmatched_rows = []

    for row in gmb_rows:
        email = str(row.get(COL_OWNER_EMAIL) or "").strip()
        phone = str(row.get(COL_OWNER_PHONE) or "").strip()
        match_val = email or phone
        if not match_val:
            continue

        ne = _norm_email(email)
        np = _norm_phone(phone)

        if (ne and ne in bs_emails) or (np and np in bs_phones):
            _upd = {COL_ACTION: "Skip", COL_CONTACT_STATUS: CROSS_LIST_STATUS["dual"]}
            matched_bs = bs_row_by_email.get(ne) or bs_row_by_phone.get(np)
            if matched_bs:
                bs_url = str(matched_bs.get(COL_BOAT_ADMIN_URL) or "").strip()
                if bs_url:
                    _upd[COL_BS_ADMIN_URL] = bs_url
            if email:
                gmb_email_updates[email] = _upd
            else:
                gmb_phone_updates[phone] = _upd
            gmb_dual += 1
        else:
            gmb_unmatched_rows.append(row)

    report(f"  GMB results so far → {gmb_dual} Dual Presence, {len(gmb_unmatched_rows)} to check further")

    # ── Layer 4+5: Check unmatched GMB rows against BS - Churn / BS - Not Live ─
    report(f"\n── Layer 4+5: Churn + Not Live matching for {len(gmb_unmatched_rows)} unmatched GMB owners ──")

    gmb_funnel      = 0
    gmb_name_match  = 0
    gmb_layer3_rows = []  # rows not matched in Layer 4+5 — go to Kustomer

    for row in gmb_unmatched_rows:
        email = str(row.get(COL_OWNER_EMAIL) or "").strip()
        phone = str(row.get(COL_OWNER_PHONE) or "").strip()
        ne    = _norm_email(email)
        np    = _norm_phone(phone)

        matched_row  = None
        source_label = ""
        name_match   = False

        if churn_by_email.get(ne) or churn_by_phone.get(np):
            matched_row  = churn_by_email.get(ne) or churn_by_phone.get(np)
            source_label = "BS Churn"
        elif not_live_by_email.get(ne) or not_live_by_phone.get(np):
            matched_row  = not_live_by_email.get(ne) or not_live_by_phone.get(np)
            source_label = "BS Not Live"
        else:
            # Name-based fallback: catches same owner using different email/phone across platforms
            nn = _norm_name(row.get(COL_FIRST_NAME, ""), row.get(COL_LAST_NAME, ""))
            if nn and churn_by_name.get(nn):
                matched_row  = churn_by_name[nn]
                source_label = "BS Churn"
                name_match   = True
            elif nn and not_live_by_name.get(nn):
                matched_row  = not_live_by_name[nn]
                source_label = "BS Not Live"
                name_match   = True

        if matched_row:
            listing_state   = str(matched_row.get("BOAT_LISTING_STATE") or "").strip()
            admin_url       = str(matched_row.get(COL_BOAT_ADMIN_URL)   or "").strip()

            if name_match:
                matched_contact = str(matched_row.get(COL_OWNER_EMAIL) or matched_row.get(COL_OWNER_PHONE) or "").strip()
                hint = f", {matched_contact}" if matched_contact else ""
                note = f"{source_label}: {listing_state} (name match, verify before outreach{hint})"
            else:
                note = f"{source_label}: {listing_state}" if listing_state else source_label

            _upd = {
                COL_ACTION:         "Manual Check",
                COL_CONTACT_STATUS: CROSS_LIST_STATUS["funnel"],
                COL_NOTES:          note,
            }
            if admin_url:
                _upd[COL_BS_ADMIN_URL] = admin_url

            if email:
                gmb_email_updates[email] = _upd
            else:
                gmb_phone_updates[phone] = _upd

            if name_match:
                gmb_name_match += 1
                report(f"  {email or phone} → {source_label} ({listing_state}) [NAME MATCH — verify]")
            else:
                gmb_funnel += 1
                report(f"  {email or phone} → {source_label} ({listing_state})")
        else:
            gmb_layer3_rows.append(row)

    report(f"  {gmb_funnel} matched by email/phone → Already on BS Funnel")
    report(f"  {gmb_name_match} matched by name only → Already on BS Funnel (verify)")
    report(f"  {len(gmb_layer3_rows)} remaining for Kustomer lookup")

    # ── Layer 3: Kustomer lookup for rows not caught by Layer 4+5 ─────────────
    report(f"\n── Layer 3: Kustomer lookup for {len(gmb_layer3_rows)} unmatched GMB owners ──")

    kustomer = None if dry_run else KustomerClient()

    for i, row in enumerate(gmb_layer3_rows, start=1):
        email     = str(row.get(COL_OWNER_EMAIL) or "").strip()
        phone     = str(row.get(COL_OWNER_PHONE) or "").strip()
        match_val = email or phone

        if dry_run:
            report(f"  [{i}/{len(gmb_unmatched_rows)}] Would look up {email or phone} in Kustomer")
            _upd = {COL_CONTACT_STATUS: CROSS_LIST_STATUS["target"], COL_ACTION: "Cross-List"}
            if email:
                gmb_email_updates[email] = _upd
            else:
                gmb_phone_updates[phone] = _upd
            gmb_cross_list += 1
            continue

        found_in_kustomer = False
        try:
            if email:
                customer = kustomer.get_customer_by_email(email)
                if customer:
                    found_in_kustomer = True

            if not found_in_kustomer and phone:
                customer = kustomer.get_customer_by_phone(phone)
                if customer:
                    found_in_kustomer = True

        except Exception as exc:
            logger.warning(f"Kustomer lookup failed for {email or phone}: {exc}")

        if found_in_kustomer:
            status = CROSS_LIST_STATUS["possible"]
            action = "Manual Check"
            gmb_possible += 1
            report(f"  [{i}] {email or phone} → found in Kustomer (Possible Dual Presence)")
        else:
            status = CROSS_LIST_STATUS["target"]
            action = "Cross-List"
            gmb_cross_list += 1

        _upd = {COL_ACTION: action, COL_CONTACT_STATUS: status}
        if email:
            gmb_email_updates[email] = _upd
        else:
            gmb_phone_updates[phone] = _upd

        time.sleep(0.3)  # be gentle with the Kustomer API

    # ── Write results back to both sheets ─────────────────────────────────────
    all_bs_updates  = {**bs_email_updates,  **bs_phone_updates}
    all_gmb_updates = {**gmb_email_updates, **gmb_phone_updates}

    if dry_run:
        report("\n[DRY RUN] Would write the following to BS Live sheet:")
        dual_count   = sum(1 for v in all_bs_updates.values() if v[COL_CONTACT_STATUS] == CROSS_LIST_STATUS["dual"])
        target_count = sum(1 for v in all_bs_updates.values() if v[COL_CONTACT_STATUS] == CROSS_LIST_STATUS["target"])
        report(f"  {dual_count} rows → Dual Presence")
        report(f"  {target_count} rows → Pending Outreach (Cross-List)")

        report("\n[DRY RUN] Would write the following to GMB Live sheet:")
        dual_g     = sum(1 for v in all_gmb_updates.values() if v[COL_CONTACT_STATUS] == CROSS_LIST_STATUS["dual"])
        funnel_g   = sum(1 for v in all_gmb_updates.values() if v[COL_CONTACT_STATUS] == CROSS_LIST_STATUS["funnel"])
        possible_g = sum(1 for v in all_gmb_updates.values() if v[COL_CONTACT_STATUS] == CROSS_LIST_STATUS["possible"])
        target_g   = sum(1 for v in all_gmb_updates.values() if v[COL_CONTACT_STATUS] == CROSS_LIST_STATUS["target"])
        report(f"  {dual_g} rows → Dual Presence")
        report(f"  {funnel_g} rows → Already on BS Funnel")
        report(f"  {possible_g} rows → Possible Dual Presence (verify)")
        report(f"  {target_g} rows → Pending Outreach (Cross-List)")
    else:
        report("\nWriting tags to BS Live sheet...")
        updated = 0
        if bs_email_updates:
            updated += bs_connector.batch_update_rows(COL_OWNER_EMAIL, bs_email_updates)
        if bs_phone_updates:
            updated += bs_connector.batch_update_rows(COL_OWNER_PHONE, bs_phone_updates)
        report(f"  {updated} rows updated in BS Live")

        report("Writing tags to GMB Live sheet...")
        updated = 0
        if gmb_email_updates:
            updated += gmb_connector.batch_update_rows(COL_OWNER_EMAIL, gmb_email_updates)
        if gmb_phone_updates:
            updated += gmb_connector.batch_update_rows(COL_OWNER_PHONE, gmb_phone_updates)
        report(f"  {updated} rows updated in GMB Live")

    # ── Summary ────────────────────────────────────────────────────────────────
    report("\n" + "─" * 50)
    report("CROSS-LIST DETECTION SUMMARY")
    report("─" * 50)
    report(f"  BS Live  ({len(bs_rows)} owners)")
    report(f"    Dual Presence       : {bs_dual}")
    report(f"    Cross-List targets  : {bs_cross_list}")
    report(f"  GMB Live ({len(gmb_rows)} owners)")
    report(f"    Dual Presence       : {gmb_dual}")
    report(f"    Already on BS Funnel: {gmb_funnel}  ← check BS listing state in Notes")
    report(f"    Name match (verify) : {gmb_name_match}  ← same name, different email/phone")
    report(f"    Possible Dual Pres. : {gmb_possible}  ← verify manually")
    report(f"    Cross-List targets  : {gmb_cross_list}")
    report("─" * 50)

    if not dry_run and gmb_possible:
        report(
            f"\n  NOTE: {gmb_possible} GMB owners were found in Kustomer but couldn't be\n"
            f"  matched by email or phone. They may already be on Boatsetter under a\n"
            f"  different contact. Check their Contact Status = 'Possible Dual Presence'\n"
            f"  in the GMB sheet before running outreach."
        )

    logger.info(
        f"cross_list complete | bs_dual={bs_dual} bs_targets={bs_cross_list} "
        f"gmb_dual={gmb_dual} gmb_funnel={gmb_funnel} gmb_name_match={gmb_name_match} "
        f"gmb_possible={gmb_possible} gmb_targets={gmb_cross_list}"
    )

    return {
        "bs_dual":          bs_dual,
        "bs_cross_list":    bs_cross_list,
        "gmb_dual":         gmb_dual,
        "gmb_funnel":       gmb_funnel,
        "gmb_name_match":   gmb_name_match,
        "gmb_possible":     gmb_possible,
        "gmb_cross_list":   gmb_cross_list,
    }


# ── CLI entry point ────────────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Detect cross-listing opportunities by comparing BS Live and GMB Live sheets.\n"
            "Tags every owner as Dual Presence, Possible Dual Presence, or Cross-List."
        )
    )
    parser.add_argument(
        "--spreadsheet-id",
        required=True,
        help="Google Sheets document ID (both BS and GMB tabs must be in this spreadsheet).",
    )
    parser.add_argument(
        "--bs-sheet",
        required=True,
        help='Tab name for the BS Live sheet, e.g. "BS - Live".',
    )
    parser.add_argument(
        "--gmb-sheet",
        required=True,
        help='Tab name for the GMB Live sheet, e.g. "GMB - Live".',
    )
    parser.add_argument(
        "--churn-sheet",
        default="BS - Churn",
        help='Tab name for churn rows (default: "BS - Churn"). Used for Layer 4 matching.',
    )
    parser.add_argument(
        "--not-live-sheet",
        default="BS - Not Live",
        help='Tab name for not-live rows (default: "BS - Not Live"). Used for Layer 5 matching.',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview results without writing anything to the sheets.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    detect_cross_list(
        spreadsheet_id=args.spreadsheet_id,
        bs_sheet_name=args.bs_sheet,
        gmb_sheet_name=args.gmb_sheet,
        churn_sheet_name=args.churn_sheet,
        not_live_sheet_name=args.not_live_sheet,
        dry_run=args.dry_run,
    )
