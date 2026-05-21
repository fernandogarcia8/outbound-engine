"""
Generates message drafts for all eligible prospect rows and writes them to
the sheet as Draft Subject / Draft Email / Draft SMS columns.

Flow:
  1. generate_drafts() -- reads eligible rows, calls get_messages(), writes draft columns
  2. Human reviews / edits drafts directly in the Google Sheet
  3. send_from_drafts() in engine.py -- reads draft columns and sends via Kustomer

Drafts are kept in the sheet after sending as a permanent record of what went out.
"""

from config import (
    COL_ACTION,
    COL_CONTACT_STATUS,
    COL_OWNER_EMAIL,
    COL_OWNER_PHONE,
    COL_FIRST_NAME,
    COL_LAST_NAME,
    COL_DRAFT_SUBJECT,
    COL_DRAFT_EMAIL,
    COL_DRAFT_SMS,
    COL_DRAFT_ASSIGNEE_ID,
    SEGMENT_COLUMN_OVERRIDES,
    SEGMENT_ACTIONS,
)
from config import TEAM_MEMBERS
from engine import normalize_row, _deduplicate_by_owner, _message_variant
from segmentation import filter_eligible_rows, has_email, has_phone
from sheets_connector import SheetsConnector
from templates import get_messages
from template_store import load_overrides as _load_template_overrides
from round_robin import get_next_assignee


def generate_drafts(
    sheet_id: str,
    sheet_name: str,
    market: str,
    dry_run: bool = False,
    test_only: bool = False,
    on_progress=None,
) -> dict:
    """
    Generates email + SMS drafts for all eligible prospect rows and writes them
    to the Draft Subject / Draft Email / Draft SMS columns in the sheet.

    Returns {"drafted": int, "skipped": int}
    """
    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    mode = "[DRY RUN] " if dry_run else ""
    report(f"{mode}Generating prospect drafts for {market}...")

    # Load per-market template overrides
    try:
        market_templates = _load_template_overrides(sheet_id)
    except Exception:
        market_templates = {}

    # Read + normalise rows
    sheets   = SheetsConnector(sheet_id, sheet_name)
    all_rows = sheets.get_all_rows()
    report(f"  {len(all_rows)} rows in sheet")

    all_rows_norm = [normalize_row(r, "prospect") for r in all_rows]

    if test_only:
        def _is_test_row(r: dict) -> bool:
            return str(r.get("Notes") or "").strip().lower() == "test"
        eligible = _deduplicate_by_owner([
            (r, 1) for r in all_rows_norm
            if _is_test_row(r) and (has_email(r) or has_phone(r))
        ])
        report(f"  [TEST ONLY] {len(eligible)} test contact(s) found")
    else:
        raw_eligible = filter_eligible_rows(all_rows_norm, "prospect")
        eligible     = _deduplicate_by_owner(raw_eligible)
    report(f"  {len(eligible)} eligible rows for drafting")

    if not eligible:
        report("Nothing to draft.")
        return {"drafted": 0, "skipped": 0}

    overrides    = SEGMENT_COLUMN_OVERRIDES.get("prospect", {})
    email_col    = overrides.get("email")  or COL_OWNER_EMAIL
    phone_col    = overrides.get("phone")  or COL_OWNER_PHONE

    # Build draft updates keyed by email (fallback phone) for batch write
    email_updates: dict[str, dict] = {}
    phone_updates: dict[str, dict] = {}
    drafted  = 0
    skipped  = 0

    for i, (row, touch) in enumerate(eligible, start=1):
        owner_email = str(row.get(COL_OWNER_EMAIL) or "").strip()
        owner_phone = str(row.get(COL_OWNER_PHONE) or "").strip()
        first       = str(row.get(COL_FIRST_NAME)  or "").strip().title()
        last        = str(row.get(COL_LAST_NAME)   or "").strip().title()
        display     = f"{first} {last}".strip() or owner_email or owner_phone

        if not owner_email and not owner_phone:
            report(f"  [{i}] {display} -- no contact info, skipped")
            skipped += 1
            continue

        # Reuse the T1 rep for follow-up drafts so the name stays consistent
        saved_rep_id = str(row.get(COL_DRAFT_ASSIGNEE_ID) or "").strip()
        if touch > 1 and saved_rep_id:
            assignee = next(
                (m for m in TEAM_MEMBERS if m["kustomer_id"] == saved_rep_id),
                get_next_assignee(),
            )
        else:
            assignee = get_next_assignee()

        variant  = _message_variant("prospect", sheet_name, row)

        try:
            messages = get_messages(
                "prospect", row, market,
                assignee_name=assignee["name"],
                touch=touch,
                variant=variant,
                market_overrides=market_templates,
            )
        except Exception as exc:
            report(f"  [{i}] {display} -- template error: {exc}, skipped")
            skipped += 1
            continue

        draft = {
            COL_DRAFT_SUBJECT:     messages["email_subject"],
            COL_DRAFT_EMAIL:       messages["email_body"],
            COL_DRAFT_SMS:         messages["sms_body"],
            COL_DRAFT_ASSIGNEE_ID: assignee["kustomer_id"],
        }

        if not dry_run:
            if owner_email:
                email_updates[owner_email] = draft
            else:
                phone_updates[owner_phone] = draft
        else:
            report(f"  [{i}/{len(eligible)}] {display}  (Touch {touch})")
            report(f"     Subject : {messages['email_subject']}")
            report(f"     Email   : {messages['email_body'][:160]}...")
            report(f"     SMS     : {messages['sms_body'][:120]}...")

        drafted += 1

    # Write all drafts in batch
    if not dry_run and (email_updates or phone_updates):
        report(f"\nWriting {drafted} draft(s) to sheet...")
        written = 0
        if email_updates:
            written += sheets.batch_update_rows(email_col, email_updates)
        if phone_updates:
            written += sheets.batch_update_rows(phone_col, phone_updates)
        report(f"  {written} rows updated")

    report(f"\n{mode}Done -- {drafted} draft(s) generated, {skipped} skipped")
    if not dry_run and drafted:
        report(f"  Open the sheet, review the Draft Subject / Draft Email / Draft SMS columns,")
        report(f"  edit any message you want, then click 'Send Drafts' when ready.")

    return {"drafted": drafted, "skipped": skipped}
