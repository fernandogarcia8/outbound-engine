"""
Reads and writes data to Google Sheets using a service account.
The service account email must be added as an Editor on any sheet you want to use.
"""

import os

import gspread
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class SheetsConnector:
    def __init__(self, spreadsheet_id: str, sheet_name: str):
        credentials_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
        if not credentials_path:
            raise EnvironmentError(
                "GOOGLE_SHEETS_CREDENTIALS_JSON must be set in .env — "
                "point it to your service account JSON file."
            )

        creds  = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        client = gspread.authorize(creds)

        self._sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)

    def get_all_rows(self) -> list[dict]:
        """Returns all rows as a list of dicts, with column headers as keys."""
        return self._sheet.get_all_records()

    def ensure_columns(self, columns: list[str]) -> None:
        """
        Adds any missing column headers to the end of row 1.
        Expands the sheet grid automatically if the new columns would exceed it.
        """
        headers  = self._sheet.row_values(1)
        existing = set(headers)
        missing  = [c for c in columns if c not in existing]
        if not missing:
            return

        needed   = len(headers) + len(missing)
        props    = self._sheet.spreadsheet.fetch_sheet_metadata()
        for s in props["sheets"]:
            if s["properties"]["sheetId"] == self._sheet.id:
                current_cols = s["properties"]["gridProperties"]["columnCount"]
                break
        else:
            current_cols = len(headers)

        if needed > current_cols:
            self._sheet.spreadsheet.batch_update({"requests": [{
                "appendDimension": {
                    "sheetId":    self._sheet.id,
                    "dimension":  "COLUMNS",
                    "length":     needed - current_cols,
                }
            }]})

        next_col = len(headers) + 1
        for col in missing:
            self._sheet.update_cell(1, next_col, col)
            next_col += 1

    def append_row(self, values: dict) -> None:
        """Appends a row using a column→value dict. Columns not in the sheet are ignored."""
        headers = self._sheet.row_values(1)
        row = [str(values.get(h, "")) for h in headers]
        self._sheet.append_row(row, value_input_option="RAW")

    def update_row(self, match_column: str, match_value: str, updates: dict) -> None:
        """
        Finds the row where match_column == match_value and writes the updates dict
        to those columns. Silently skips columns that don't exist in the sheet.
        """
        headers    = self._sheet.row_values(1)
        all_values = self._sheet.get_all_values()
        data_rows  = all_values[1:]

        if match_column not in headers:
            raise ValueError(f"Column '{match_column}' not found in sheet headers.")

        match_col_index = headers.index(match_column)

        target_row_index = None
        for i, row in enumerate(data_rows):
            cell_value = row[match_col_index] if match_col_index < len(row) else ""
            if cell_value.strip() == match_value.strip():
                target_row_index = i + 2  # +1 for header row, +1 for 1-based index
                break

        if target_row_index is None:
            raise ValueError(
                f"No row found where '{match_column}' == '{match_value}'"
            )

        for col_name, new_value in updates.items():
            if col_name not in headers:
                continue
            col_index = headers.index(col_name) + 1
            self._sheet.update_cell(target_row_index, col_index, new_value)

    def batch_update_rows(
        self, match_column: str, updates: dict[str, dict]
    ) -> int:
        """
        Updates multiple rows in a single API call — much faster than calling
        update_row() in a loop for large sheets.

        Args:
            match_column: Column to match on (e.g. "OWNER_EMAIL")
            updates: {match_value: {column_name: new_value, ...}}

        Returns:
            Number of rows actually updated.
        """
        headers    = self._sheet.row_values(1)
        all_values = self._sheet.get_all_values()
        data_rows  = all_values[1:]

        if match_column not in headers:
            raise ValueError(f"Column '{match_column}' not found in sheet headers.")

        match_col_idx = headers.index(match_column)

        # Ensure all target columns exist — preserve insertion order so callers
        # can control which column appears first in the sheet.
        seen = set()
        all_target_cols = []
        for row_upd in updates.values():
            for col in row_upd:
                if col not in seen:
                    all_target_cols.append(col)
                    seen.add(col)
        self.ensure_columns(all_target_cols)

        # Re-read headers in case we just added columns
        headers = self._sheet.row_values(1)

        cell_updates = []
        rows_updated = 0

        for row_idx, row in enumerate(data_rows):
            cell_val = (row[match_col_idx] if match_col_idx < len(row) else "").strip()
            if cell_val not in updates:
                continue

            sheet_row  = row_idx + 2  # 1-based + header offset
            row_updates = updates[cell_val]
            rows_updated += 1

            for col_name, new_val in row_updates.items():
                if col_name not in headers:
                    continue
                col_idx = headers.index(col_name) + 1
                cell_updates.append({
                    "range":  rowcol_to_a1(sheet_row, col_idx),
                    "values": [[new_val]],
                })

        if cell_updates:
            self._sheet.batch_update(cell_updates)

        return rows_updated

    def ensure_column_after(self, after_col: str, new_col: str) -> None:
        """
        Ensures new_col exists immediately after after_col.
        No-op if new_col already exists anywhere in the sheet.
        Falls back to appending at the end if after_col is not found.
        """
        headers = self._sheet.row_values(1)
        if new_col in headers:
            return

        insert_at = headers.index(after_col) + 1 if after_col in headers else len(headers)

        self._sheet.spreadsheet.batch_update({"requests": [{
            "insertDimension": {
                "range": {
                    "sheetId":    self._sheet.id,
                    "dimension":  "COLUMNS",
                    "startIndex": insert_at,
                    "endIndex":   insert_at + 1,
                },
                "inheritFromBefore": True,
            }
        }]})
        self._sheet.update_cell(1, insert_at + 1, new_col)

    def fill_defaults(self, defaults: dict[str, str], dry_run: bool = False) -> int:
        """
        For each column in `defaults`, writes the default value into any blank
        cell in that column. Skips rows that are entirely empty. Only touches
        cells that are currently blank — never overwrites existing values.

        Returns the number of data rows that had at least one cell filled.
        """
        self.ensure_columns(list(defaults.keys()))
        headers    = self._sheet.row_values(1)
        all_values = self._sheet.get_all_values()
        data_rows  = all_values[1:]

        cell_updates = []
        rows_touched = set()

        for row_idx, row in enumerate(data_rows):
            if not any(cell.strip() for cell in row):
                continue  # skip blank rows

            sheet_row = row_idx + 2  # 1-based + header offset

            for col_name, default_val in defaults.items():
                if col_name not in headers:
                    continue
                col_idx  = headers.index(col_name)
                cell_val = row[col_idx] if col_idx < len(row) else ""
                if not cell_val.strip():
                    cell_updates.append({
                        "range":  rowcol_to_a1(sheet_row, col_idx + 1),
                        "values": [[default_val]],
                    })
                    rows_touched.add(row_idx)

        if cell_updates and not dry_run:
            self._sheet.batch_update(cell_updates)

        return len(rows_touched)

    def fill_computed_column(
        self, source_col: str, target_col: str, compute_fn, dry_run: bool = False
    ) -> int:
        """
        For each row where source_col has a value but target_col is blank,
        writes compute_fn(source_value) into target_col.

        Idempotent — only fills blank cells. Returns number of rows filled.
        Silently returns 0 if source_col doesn't exist (sheet doesn't need it).
        """
        headers = self._sheet.row_values(1)
        if source_col not in headers:
            return 0

        if not dry_run:
            self.ensure_columns([target_col])
            headers = self._sheet.row_values(1)

        if target_col not in headers:
            return 0

        all_values = self._sheet.get_all_values()
        data_rows  = all_values[1:]

        src_idx = headers.index(source_col)
        tgt_idx = headers.index(target_col)

        cell_updates = []
        rows_filled  = 0

        for row_idx, row in enumerate(data_rows):
            if not any(cell.strip() for cell in row):
                continue
            src_val = str(row[src_idx]).strip() if src_idx < len(row) else ""
            tgt_val = (row[tgt_idx] if tgt_idx < len(row) else "")
            tgt_val = str(tgt_val).strip()
            if src_val and not tgt_val:
                cell_updates.append({
                    "range":  rowcol_to_a1(row_idx + 2, tgt_idx + 1),
                    "values": [[compute_fn(src_val)]],
                })
                rows_filled += 1

        if cell_updates and not dry_run:
            self._sheet.batch_update(cell_updates)

        return rows_filled

    def apply_column_dropdowns(
        self,
        config: dict,
        dry_run: bool = False,
    ) -> list:
        """
        Applies dropdown validation and background-color conditional formatting
        to the listed columns.

        config format:
            {
                "Column Name": [
                    ("Option text", (red, green, blue)),  # floats 0.0–1.0
                    ...
                ],
                ...
            }

        Data validation is idempotent (replaces existing).
        Existing conditional format rules for the target columns are deleted
        first so re-running this is safe.

        Returns the list of column names that were actually updated.
        """
        ws       = self._sheet
        ss       = ws.spreadsheet
        sheet_id = ws.id
        headers  = ws.row_values(1)

        target_cols = {name: headers.index(name) for name in config if name in headers}
        if not target_cols:
            return []

        if dry_run:
            return list(target_cols.keys())

        requests = []

        # ── Delete ALL existing conditional format rules on this sheet ─────────
        # Wipe clean before reapplying so stale rules can never persist.
        try:
            raw = ss.client.request(
                "GET",
                f"https://sheets.googleapis.com/v4/spreadsheets/{ss.id}",
                params={"fields": "sheets(conditionalFormats,properties/sheetId)"},
            )
            sheets_data = raw.json().get("sheets", [])
        except Exception:
            sheets_data = []

        existing = []
        for s in sheets_data:
            if s.get("properties", {}).get("sheetId") == sheet_id:
                existing = s.get("conditionalFormats", [])
                break

        for idx in range(len(existing) - 1, -1, -1):
            requests.append({
                "deleteConditionalFormatRule": {"sheetId": sheet_id, "index": idx}
            })

        # ── Add validation + color rules for each column ──────────────────────
        for col_name, options in config.items():
            if col_name not in target_cols:
                continue
            col_idx = target_cols[col_name]

            col_range = {
                "sheetId":          sheet_id,
                "startRowIndex":    1,
                "startColumnIndex": col_idx,
                "endColumnIndex":   col_idx + 1,
            }

            requests.append({
                "setDataValidation": {
                    "range": col_range,
                    "rule": {
                        "condition": {
                            "type":   "ONE_OF_LIST",
                            "values": [{"userEnteredValue": v} for v, _ in options],
                        },
                        "showCustomUi": True,
                        "strict":       False,
                    },
                }
            })

            for value, (r, g, b) in options:
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [col_range],
                            "booleanRule": {
                                "condition": {
                                    "type":   "TEXT_EQ",
                                    "values": [{"userEnteredValue": value}],
                                },
                                "format": {
                                    "backgroundColor": {"red": r, "green": g, "blue": b}
                                },
                            },
                        },
                        "index": 0,
                    }
                })

        if requests:
            ss.batch_update({"requests": requests})

        return list(target_cols.keys())
