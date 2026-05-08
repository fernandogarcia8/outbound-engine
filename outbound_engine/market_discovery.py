"""
Discovers markets by scanning Google Drive.

Two modes:
  - MARKETS_DRIVE_FOLDER_ID is set in .env → scans that specific folder only
  - Not set → lists all spreadsheets the service account has access to

Either way, every spreadsheet found becomes a market. The spreadsheet name
becomes the display name. Tab names default to the standard set.
"""

import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

DEFAULT_SHEET_TABS = {
    "bs_live":     "BS - Live",
    "gmb_live":    "GMB - Live",
    "bs_not_live": "BS - Not Live",
    "bs_churn":    "BS - Churn",
    "prospects":   "Prospects",
}


def discover_markets(credentials_path: str = "", folder_id: str = "") -> dict:
    """
    Scans Drive and returns a markets dict keyed by slugified market name.

    Args:
        credentials_path: Path to the service account JSON file.
        folder_id:        Google Drive folder ID to scan. If empty, all
                          spreadsheets accessible to the service account are used.

    Returns:
        {
          "savannah": {
            "display_name": "Savannah",
            "sheet_id": "1ABC...",
            "sheets": { "bs_live": "BS - Live", ... }
          },
          ...
        }
    """
    creds_path = credentials_path or os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    if not creds_path or not os.path.exists(creds_path):
        return {}

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    import re

    if folder_id:
        # Fetch both real spreadsheets and shortcuts (Drive creates shortcuts
        # when a file is "moved" into a folder it doesn't natively live in).
        result = drive.files().list(
            q=(
                f"'{folder_id}' in parents and trashed=false and ("
                f"mimeType='application/vnd.google-apps.spreadsheet' or "
                f"mimeType='application/vnd.google-apps.shortcut')"
            ),
            fields="files(id,name,mimeType,shortcutDetails)",
            orderBy="name",
        ).execute()

        files = []
        for f in result.get("files", []):
            if f["mimeType"] == "application/vnd.google-apps.shortcut":
                target = f.get("shortcutDetails", {})
                if target.get("targetMimeType") == "application/vnd.google-apps.spreadsheet":
                    files.append({"id": target["targetId"], "name": f["name"]})
            else:
                files.append({"id": f["id"], "name": f["name"]})
    else:
        result = drive.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
            fields="files(id,name)",
            orderBy="name",
        ).execute()
        files = result.get("files", [])

    # Suffixes that are operational labels, not part of the market name
    _STRIP = re.compile(
        r"\s*[-–]\s*(outbound|prospecting)$|\s+(outbound|prospecting)$",
        re.IGNORECASE,
    )

    markets = {}
    for f in files:
        name         = f["name"]
        display_name = _STRIP.sub("", name).strip()
        key          = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        markets[key] = {
            "display_name": display_name,
            "sheet_id":     f["id"],
            "sheets":       DEFAULT_SHEET_TABS.copy(),
        }

    return markets
