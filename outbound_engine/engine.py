"""
Main orchestrator. Runs an outreach campaign for a given segment and market.

Three-touch sequence per contact (2-day gap between touches):
  Touch 1 — initial outreach  (Contact Status: Pending Outreach → Contacted)
  Touch 2 — first follow-up   (runs >= 2 days after Touch 1, no reply)
  Touch 3 — final follow-up   (runs >= 2 days after Touch 2, no reply)

CLI usage:
    python engine.py --segment reactivate --market "Panama City" \\
        --sheet-id 1vOYXzq... --sheet-name "BS - Not Live"

    python engine.py --segment prospect --market "Orlando" \\
        --sheet-id 1MgOCGT... --sheet-name "GMB - Live" --dry-run

Web app note:
    The core logic lives in run_campaign(). Pass on_progress= to stream
    output and require_approval=False to skip the CLI approval prompt.
"""

import argparse
import time
from datetime import datetime, timezone

from config import (
    SEGMENTS,
    COL_OWNER_EMAIL,
    COL_OWNER_PHONE,
    COL_FIRST_NAME,
    COL_LAST_NAME,
    COL_KUSTOMER_ID,
    COL_CONTACT_STATUS,
    COL_EMAIL_1,
    COL_SMS_1,
    COL_EMAIL_2,
    COL_SMS_2,
    COL_EMAIL_3,
    COL_SMS_3,
    COL_KUSTOMER_LINK,
    SEGMENT_COLUMN_OVERRIDES,
    REACTIVATE_RECENT_DAYS,
)
from kustomer_client import KustomerClient
from sheets_connector import SheetsConnector
from segmentation import filter_eligible_rows, has_email, has_phone
from templates import get_messages
from template_store import load_overrides as _load_template_overrides
from round_robin import get_next_assignee
from logger import setup_file_logger, now_iso, RunSummary

# Maps touch number → (email_col, sms_col) to write timestamps into
_TOUCH_COLS = {
    1: (COL_EMAIL_1, COL_SMS_1),
    2: (COL_EMAIL_2, COL_SMS_2),
    3: (COL_EMAIL_3, COL_SMS_3),
}

_TOUCH_LABELS = {1: "initial", 2: "follow-up", 3: "final"}


_COL_LAST_LIVE = "BOAT_LISTING_LAST_LIVE_ON_SITE_AT"


def _reactivate_variant(row: dict) -> str:
    """Returns "recent" if last-live date is within REACTIVATE_RECENT_DAYS, else "old"."""
    last_live = (row.get(_COL_LAST_LIVE) or "").strip()
    if not last_live:
        return "old"
    try:
        ts = datetime.strptime(last_live[:19], "%Y-%m-%d %H:%M:%S")
        return "recent" if (datetime.utcnow() - ts).days < REACTIVATE_RECENT_DAYS else "old"
    except ValueError:
        return "old"


def _deduplicate_by_owner(
    eligible: list[tuple[dict, int]]
) -> list[tuple[dict, int]]:
    """
    Collapses multiple rows for the same owner (matched by email, fallback phone)
    into one, keeping the first row and setting _boat_count so templates can
    use the right noun (boat / boats / fleet).
    """
    import re as _re

    def _norm(val: str) -> str:
        return val.lower().strip()

    seen: dict[str, list] = {}   # key → [row, touch, count]
    order: list[str] = []

    for row, touch in eligible:
        email = str(row.get(COL_OWNER_EMAIL) or "").strip()
        phone = str(row.get(COL_OWNER_PHONE) or "").strip()
        key   = _norm(email) if email else _re.sub(r"\D", "", phone)
        if not key:
            continue

        if key in seen:
            seen[key][2] += 1
        else:
            seen[key] = [row, touch, 1]
            order.append(key)

    result = []
    for key in order:
        row, touch, count = seen[key]
        row = dict(row)
        row["_boat_count"] = count
        result.append((row, touch))

    return result


def _message_variant(segment: str, sheet_name: str, row: dict) -> str | None:
    """Determines the message variant to use based on segment + sheet context."""
    if segment == "reactivate":
        return _reactivate_variant(row)
    if segment == "cross_list":
        return "gmb" if sheet_name.upper().startswith("GMB") else "bs"
    return None


def normalize_row(row: dict, segment: str) -> dict:
    """
    Copies non-standard column values into the standard column names so all
    downstream code can work with a single consistent field set.

    Example: prospect sheets use "Email" → gets copied to "OWNER_EMAIL".
    The original keys are kept so nothing is lost.
    """
    overrides = SEGMENT_COLUMN_OVERRIDES.get(segment, {})
    if not overrides:
        return row

    normalized = dict(row)

    email_col = overrides.get("email")
    if email_col and email_col in row:
        normalized[COL_OWNER_EMAIL] = row[email_col]

    phone_col = overrides.get("phone")
    if phone_col and phone_col in row:
        normalized[COL_OWNER_PHONE] = row[phone_col]

    name_col = overrides.get("first_name")
    if name_col and name_col in row:
        full = (row[name_col] or "").strip()
        parts = full.split(" ", 1)
        normalized[COL_FIRST_NAME] = parts[0]
        normalized[COL_LAST_NAME]  = parts[1] if len(parts) > 1 else ""

    return normalized


def _print_preview(
    eligible: list[tuple[dict, int]], segment: str, market: str, report
) -> None:
    """Prints a contact table so the user can review before approving the send."""
    rule = "━" * 66
    report("")
    report(rule)
    report(f"  OUTREACH PREVIEW — {segment} · {market}")
    report(rule)
    report(f"  {'#':<5} {'Name':<22} {'Contact':<28} {'T':<3} Boats")
    report(f"  {'─'*5} {'─'*22} {'─'*28} {'─'*3} ─────")

    touch_counts: dict[int, int] = {}
    for i, (row, touch) in enumerate(eligible, 1):
        first      = str(row.get(COL_FIRST_NAME) or "").strip().title()
        last       = str(row.get(COL_LAST_NAME)  or "").strip().title()
        name       = f"{first} {last}".strip() or "—"
        email      = str(row.get(COL_OWNER_EMAIL) or "").strip()
        phone      = str(row.get(COL_OWNER_PHONE) or "").strip()
        contact    = email or phone or "—"
        boat_count = int(row.get("_boat_count") or 1)

        if len(name) > 22:    name    = name[:20]    + ".."
        if len(contact) > 28: contact = contact[:26] + ".."

        touch_counts[touch] = touch_counts.get(touch, 0) + 1
        report(f"  {i:<5} {name:<22} {contact:<28} {touch:<3} {boat_count}")

    report(f"  {'─'*5} {'─'*22} {'─'*28} {'─'*3} ─────")
    parts = [
        f"T{t} ({_TOUCH_LABELS[t]}): {touch_counts[t]}"
        for t in sorted(touch_counts)
    ]
    report(f"  {' · '.join(parts)} · Total: {len(eligible)}")
    report(rule)
    report("")


def _ask_approval(count: int) -> bool:
    label = f"{count} contact{'s' if count != 1 else ''}"
    try:
        answer = input(f"  Send outreach to {label}? [y/N] ").strip().lower()
        return answer == "y"
    except (KeyboardInterrupt, EOFError):
        print("")
        return False


def run_campaign(
    segment: str,
    market: str,
    sheet_id: str,
    sheet_name: str,
    dry_run: bool = False,
    sms_only: bool = False,
    test_only: bool = False,
    require_approval: bool = True,
    on_progress=None,
) -> dict:
    """
    Executes an outreach campaign for the given segment and market.

    Args:
        segment:          One of: reactivate, get_live, relist, prospect, cross_list
        market:           Market name injected into templates, e.g. "Panama City"
        sheet_id:         Google Sheets document ID
        sheet_name:       Tab name within the spreadsheet
        dry_run:          If True, previews what would be sent but makes no API calls
        require_approval: If True (default), shows a contact preview and prompts
                          for confirmation before sending. Pass False when calling
                          from a web layer that handles approval externally.
        on_progress:      Optional callback(str) for each progress message.
                          If None, messages are printed to stdout.

    Returns:
        A dict with the run summary (total, contacted, skipped, errors).
    """

    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    logger  = setup_file_logger(run_timestamp)
    summary = RunSummary()

    mode_label = "[DRY RUN] " if dry_run else ""
    report(f"{mode_label}Starting campaign: segment={segment}, market={market}")
    logger.info(f"{mode_label}segment={segment} market={market} sheet_id={sheet_id} sheet_name={sheet_name}")

    # ── Load per-market template overrides ───────────────────────────────────
    try:
        _market_templates = _load_template_overrides(sheet_id)
        if _market_templates:
            logger.info(f"Loaded {len(_market_templates)} template override(s).")
    except Exception as exc:
        _market_templates = {}
        logger.warning(f"Could not load template overrides: {exc}")

    # ── Load data ─────────────────────────────────────────────────────────────
    report("Reading rows from Google Sheets...")
    sheets = SheetsConnector(sheet_id, sheet_name)
    all_rows = sheets.get_all_rows()
    report(f"Found {len(all_rows)} total rows in sheet.")

    all_rows_normalized = [normalize_row(r, segment) for r in all_rows]

    if test_only:
        # Bypass eligibility + touch-timing checks entirely.
        # Always send Touch 1 to every row where Notes = "test" (or OWNER_ID = "test").
        # This lets test contacts be reused across runs without resetting the sheet.
        def _is_test_row(r: dict) -> bool:
            notes    = str(r.get("Notes")    or "").strip().lower()
            owner_id = str(r.get("OWNER_ID") or "").strip().lower()
            return notes == "test" or owner_id == "test"
        eligible = [
            (r, 1) for r in all_rows_normalized
            if _is_test_row(r) and (has_email(r) or has_phone(r))
        ]
        report(f"[TEST ONLY] Found {len(eligible)} test contact(s).")
    else:
        raw_eligible = filter_eligible_rows(all_rows_normalized, segment)
        eligible     = _deduplicate_by_owner(raw_eligible)

    summary.total_eligible = len(eligible)
    report(f"{len(eligible)} rows eligible for segment '{segment}'.")

    if not eligible:
        report("Nothing to do — exiting.")
        summary.print_summary(logger)
        return _summary_dict(summary)

    # ── Preview + approval gate ───────────────────────────────────────────────
    _print_preview(eligible, segment, market, report)

    if dry_run:
        report(f"{mode_label}Message preview (first 120 chars per field):")
        for i, (row, touch) in enumerate(eligible, start=1):
            owner_email = str(row.get(COL_OWNER_EMAIL) or "").strip()
            owner_phone = str(row.get(COL_OWNER_PHONE) or "").strip()
            first_name  = str(row.get(COL_FIRST_NAME)  or "").strip()
            last_name   = str(row.get(COL_LAST_NAME)   or "").strip()
            full_name   = f"{first_name} {last_name}".strip() or owner_email or owner_phone
            assignee    = get_next_assignee()
            variant     = _message_variant(segment, sheet_name, row)
            messages    = get_messages(
                segment, row, market,
                assignee_name=assignee["name"], touch=touch, variant=variant,
                market_overrides=_market_templates,
            )

            report(f"\n[{i}/{len(eligible)}] {full_name}  (Touch {touch} — {_TOUCH_LABELS[touch]})")
            report(f"  → Assign to: {assignee['name']}")
            if has_email(row) and not sms_only:
                report(f"  → EMAIL to {owner_email}")
                report(f"     Subject : {messages['email_subject']}")
                report(f"     Body    : {messages['email_body'][:120]}...")
            if has_phone(row):
                report(f"  → SMS to {owner_phone}")
                report(f"     Body    : {messages['sms_body'][:120]}...")
            if sms_only and has_email(row):
                report(f"  → (email skipped — sms-only mode)")

        report("")
        report(f"{mode_label}Dry run complete — no messages sent.")
        summary.print_summary(logger)
        return _summary_dict(summary)

    # CLI approval (skipped when called from a web layer)
    if require_approval and on_progress is None:
        if not _ask_approval(len(eligible)):
            report("Aborted.")
            return _summary_dict(summary)

    # ── Set up Kustomer client ────────────────────────────────────────────────
    kustomer = KustomerClient()

    # Resolve actual sheet column names for matching (prospect sheets use overrides)
    _overrides        = SEGMENT_COLUMN_OVERRIDES.get(segment, {})
    _email_sheet_col  = _overrides.get("email")  or COL_OWNER_EMAIL
    _phone_sheet_col  = _overrides.get("phone")  or COL_OWNER_PHONE

    # ── Process each owner ────────────────────────────────────────────────────
    for i, (row, touch) in enumerate(eligible, start=1):
        owner_email = str(row.get(COL_OWNER_EMAIL) or "").strip()
        owner_phone = str(row.get(COL_OWNER_PHONE) or "").strip()
        first_name  = str(row.get(COL_FIRST_NAME)  or "").strip()
        last_name   = str(row.get(COL_LAST_NAME)   or "").strip()
        full_name   = f"{first_name} {last_name}".strip() or owner_email or owner_phone

        match_col = _email_sheet_col if owner_email else _phone_sheet_col
        match_val = owner_email      if owner_email else owner_phone

        report(f"\n[{i}/{len(eligible)}] {full_name}  (Touch {touch} — {_TOUCH_LABELS[touch]})")

        assignee = get_next_assignee()
        variant  = _message_variant(segment, sheet_name, row)
        messages = get_messages(
            segment, row, market,
            assignee_name=assignee["name"], touch=touch, variant=variant,
            market_overrides=_market_templates,
        )
        email_col, sms_col = _TOUCH_COLS[touch]
        email_sent = False
        sms_sent   = False

        try:
            # 1. Resolve Kustomer ID
            kustomer_id = kustomer.get_or_create_customer(row)
            report(f"  → Kustomer ID: {kustomer_id}")

            # 2. Write Kustomer ID back to sheet if it wasn't there
            if not (row.get(COL_KUSTOMER_ID) or "").strip():
                sheets.update_row(match_col, match_val, {COL_KUSTOMER_ID: kustomer_id})

            # 3. Create a new conversation for this touch
            conversation = kustomer.create_conversation(
                customer_id=kustomer_id,
                assigned_user_id=assignee["kustomer_id"],
                segment=segment,
                market=market,
            )
            conversation_id = conversation["id"]
            report(f"  → Conversation created, assigned to {assignee['name']}")

        except Exception as exc:
            summary.record_error()
            report(f"  → ERROR (setup): {exc} — skipping this owner.")
            logger.error(f"FAIL | {full_name} | touch={touch} | setup | {exc}")
            continue

        # 4. Send email — independent try so SMS still runs if email fails
        if has_email(row) and not sms_only:
            try:
                kustomer.send_email(
                    customer_id=kustomer_id,
                    conversation_id=conversation_id,
                    subject=messages["email_subject"],
                    body=messages["email_body"],
                    to_email=owner_email,
                    to_name=full_name,
                )
                email_sent = True
                report(f"  → Email sent to {owner_email} ✓")
            except Exception as exc:
                report(f"  → Email FAILED: {exc}")
                logger.error(f"EMAIL FAIL | {full_name} | {exc}")

        # 5. Send SMS — independent try so sheet update still runs if SMS fails
        if has_phone(row):
            try:
                kustomer.send_sms(
                    customer_id=kustomer_id,
                    conversation_id=conversation_id,
                    body=messages["sms_body"],
                    to_phone=owner_phone,
                )
                sms_sent = True
                report(f"  → SMS sent to {owner_phone} ✓")
            except Exception as exc:
                report(f"  → SMS FAILED: {exc}")
                logger.error(f"SMS FAIL | {full_name} | {exc}")

        # 6. Write results back to sheet (always runs, captures whatever succeeded)
        try:
            timestamp     = now_iso()
            kustomer_link = (
                f"https://boatsetter.kustomerapp.com/app/customers/"
                f"{kustomer_id}/event/{conversation_id}"
            )
            sheet_updates = {COL_KUSTOMER_LINK: kustomer_link}
            if touch == 1:
                sheet_updates[COL_CONTACT_STATUS] = "Contacted"
            if email_sent:
                sheet_updates[email_col] = timestamp
            if sms_sent:
                sheet_updates[sms_col] = timestamp

            sheets.update_row(match_col, match_val, sheet_updates)
            report(f"  → Sheet updated ✓")
        except Exception as exc:
            report(f"  → Sheet update FAILED: {exc}")
            logger.error(f"SHEET FAIL | {full_name} | {exc}")

        if email_sent or sms_sent:
            summary.record_sent(email_sent, sms_sent)
        else:
            summary.record_error()

        logger.info(
            f"{'OK' if email_sent or sms_sent else 'PARTIAL'} | {full_name} | "
            f"touch={touch} email={email_sent} sms={sms_sent} "
            f"| assigned={assignee['name']} | conversation={conversation_id}"
        )

        # Respect Kustomer rate limits
        time.sleep(0.5)

    # ── Final summary ─────────────────────────────────────────────────────────
    report("")
    summary.print_summary(logger)

    return _summary_dict(summary)


def _summary_dict(summary: RunSummary) -> dict:
    return {
        "total_eligible":  summary.total_eligible,
        "total_contacted": summary.total_contacted(),
        "sent_email_only": summary.sent_email,
        "sent_sms_only":   summary.sent_sms,
        "sent_both":       summary.sent_both,
        "skipped":         summary.skipped,
        "errors":          summary.errors,
    }


# ── CLI entry point ────────────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Boatsetter Outbound Engine — send email and SMS via Kustomer"
    )
    parser.add_argument(
        "--segment",
        required=True,
        choices=SEGMENTS,
        help="Which segment to run outreach for.",
    )
    parser.add_argument(
        "--market",
        required=True,
        help='Market name injected into message templates. E.g. "Panama City"',
    )
    parser.add_argument(
        "--sheet-id",
        required=True,
        help="Google Sheets document ID (the long string in the sheet URL).",
    )
    parser.add_argument(
        "--sheet-name",
        required=True,
        help="Tab name within the spreadsheet, e.g. 'BS - Not Live'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be sent without making any API calls.",
    )
    parser.add_argument(
        "--sms-only",
        action="store_true",
        help="Send SMS only — skip email even if an email address is available. Use for GMB - Live outreach.",
    )
    parser.add_argument(
        "--test-only",
        action="store_true",
        help="Only process rows where OWNER_ID = 'test'. Use for test runs before going live.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the approval prompt and send immediately (use with care).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_campaign(
        segment=args.segment,
        market=args.market,
        sheet_id=args.sheet_id,
        sheet_name=args.sheet_name,
        dry_run=args.dry_run,
        sms_only=args.sms_only,
        test_only=args.test_only,
        require_approval=not args.yes,
    )
