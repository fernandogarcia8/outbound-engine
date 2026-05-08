"""
Market registry — auto-discovered from Google Drive.

To add a new market:
  1. Create a Google Sheets document named after the market (e.g. "Panama City")
  2. Either place it in the configured Drive folder (MARKETS_DRIVE_FOLDER_ID in .env)
     or share it with the service account email.
  3. The market will appear in the app dropdown automatically.

Tab names inside each spreadsheet must follow the standard convention:
  BS - Live | GMB - Live | BS - Not Live | BS - Churn | Prospects

To scope discovery to a specific folder, set in .env:
  MARKETS_DRIVE_FOLDER_ID=<folder-id-from-drive-url>
If not set, all spreadsheets the service account can access are treated as markets.
"""

import os
from market_discovery import discover_markets


def get_markets() -> dict:
    creds  = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    folder = os.getenv("MARKETS_DRIVE_FOLDER_ID", "")
    return discover_markets(credentials_path=creds, folder_id=folder)
