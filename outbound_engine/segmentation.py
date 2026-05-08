"""
Decides which rows from the sheet are eligible for outreach in a given segment,
and which touch number (1, 2, or 3) should be sent next.

Touch rules:
  Touch 1 — Contact Status = "Pending Outreach", no prior sends
  Touch 2 — Status = "Contacted", Touch 1 sent, >= TOUCH_GAP_DAYS ago, no reply
  Touch 3 — Status = "Contacted", Touch 2 sent, >= TOUCH_GAP_DAYS ago, no reply
"""

from datetime import datetime

from config import (
    COL_OWNER_EMAIL,
    COL_OWNER_PHONE,
    COL_ACTION,
    COL_CONTACT_STATUS,
    COL_REPLIED,
    COL_EMAIL_1,
    COL_SMS_1,
    COL_EMAIL_2,
    COL_SMS_2,
    COL_EMAIL_3,
    COL_SMS_3,
    SEGMENT_ACTIONS,
    TOUCH_GAP_DAYS,
)


def has_email(row: dict) -> bool:
    return bool((row.get(COL_OWNER_EMAIL) or "").strip())


def has_phone(row: dict) -> bool:
    return bool(str(row.get(COL_OWNER_PHONE) or "").strip())


def _days_since(timestamp_str: str) -> float:
    """Returns fractional days elapsed since a date or ISO 8601 timestamp (UTC)."""
    s = (timestamp_str or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            ts = datetime.strptime(s, fmt)
            return (datetime.utcnow() - ts).total_seconds() / 86400
        except ValueError:
            continue
    return 0.0


def get_touch_for_row(row: dict, segment: str) -> int | None:
    """
    Returns 1, 2, or 3 for the next touch this row should receive,
    or None if it is not eligible for any touch right now.
    """
    replied = (row.get(COL_REPLIED) or "").strip().lower()
    if replied == "true":
        return None

    action = (row.get(COL_ACTION) or "").strip()
    if action != SEGMENT_ACTIONS.get(segment, ""):
        return None

    status = (row.get(COL_CONTACT_STATUS) or "").strip()
    email1 = (row.get(COL_EMAIL_1) or "").strip()
    sms1   = (row.get(COL_SMS_1)   or "").strip()
    email2 = (row.get(COL_EMAIL_2) or "").strip()
    sms2   = (row.get(COL_SMS_2)   or "").strip()
    email3 = (row.get(COL_EMAIL_3) or "").strip()
    sms3   = (row.get(COL_SMS_3)   or "").strip()

    if status == "Pending Outreach" and not email1 and not sms1:
        return 1

    if status == "Contacted":
        t1_ts = email1 or sms1
        t2_ts = email2 or sms2

        if t1_ts and not email2 and not sms2:
            return 2 if _days_since(t1_ts) >= TOUCH_GAP_DAYS else None

        if t2_ts and not email3 and not sms3:
            return 3 if _days_since(t2_ts) >= TOUCH_GAP_DAYS else None

    return None


def filter_eligible_rows(rows: list[dict], segment: str) -> list[tuple[dict, int]]:
    """
    Returns (row, touch_number) pairs for all rows ready for outreach
    in the given segment, across all three touch points.
    """
    if segment not in SEGMENT_ACTIONS:
        raise ValueError(
            f"Unknown segment '{segment}'. Valid options: {list(SEGMENT_ACTIONS.keys())}"
        )

    eligible = []
    for row in rows:
        if not has_email(row) and not has_phone(row):
            continue
        touch = get_touch_for_row(row, segment)
        if touch is not None:
            eligible.append((row, touch))

    return eligible
