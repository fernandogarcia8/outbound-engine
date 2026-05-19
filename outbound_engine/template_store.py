"""
Per-market template overrides stored in a '_templates' tab in each market's
Google Sheet.

Tab format — 2 columns:
    template_key              | content
    reactivate_recent_t1_sms  | {greeting}\n\n{rep} here from Boatsetter...

Supported placeholders in content strings:
    {greeting}     "Hi John," or "Hi there,"
    {market}       market name (e.g. "Savannah")
    {rep}          rep / assignee name (or "Casey" for prospects)
    {boat_noun}    "your boat" / "your boats" / "your fleet"
    {charter_name} charter business name (prospect templates)
    {name_ref}     "I came across X" or "I came across your operation"
    {activity_ref} ", including fishing trips," or "" (may be empty)
"""

import os
import gspread
from gspread.http_client import BackOffHTTPClient
from google.oauth2.service_account import Credentials

TEMPLATES_TAB = "_templates"

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _spreadsheet(spreadsheet_id: str):
    creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
    if not creds_path:
        raise EnvironmentError("GOOGLE_SHEETS_CREDENTIALS_JSON not set")
    creds  = Credentials.from_service_account_file(creds_path, scopes=_SCOPES)
    client = gspread.Client(auth=creds, http_client=BackOffHTTPClient)
    return client.open_by_key(spreadsheet_id)


def load_overrides(spreadsheet_id: str) -> dict[str, str]:
    """
    Returns {template_key: content} for all saved overrides.
    Returns an empty dict if the _templates tab doesn't exist yet.
    """
    try:
        ws   = _spreadsheet(spreadsheet_id).worksheet(TEMPLATES_TAB)
        rows = ws.get_all_values()
        return {
            row[0]: row[1]
            for row in rows[1:]  # skip header row
            if len(row) >= 2 and row[0].strip() and row[1].strip()
        }
    except gspread.exceptions.WorksheetNotFound:
        return {}


def save_overrides(spreadsheet_id: str, overrides: dict[str, str]) -> None:
    """
    Writes all overrides to the _templates tab, creating it if it doesn't exist.
    Completely replaces tab content — pass the full overrides dict each time.
    Keys with blank content are skipped.
    """
    ss = _spreadsheet(spreadsheet_id)
    try:
        ws = ss.worksheet(TEMPLATES_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = ss.add_worksheet(title=TEMPLATES_TAB, rows=200, cols=2)

    rows = [["template_key", "content"]]
    rows += [[k, v] for k, v in sorted(overrides.items()) if v and v.strip()]

    ws.clear()
    ws.update(rows, value_input_option="RAW")
