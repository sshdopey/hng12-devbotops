from google.oauth2 import service_account
from googleapiclient.discovery import build
from typing import Dict, Any, Tuple, Optional


class Sheet:
    def __init__(self, spreadsheet_id: str, columns: Dict[str, str]):
        """Initialize Sheet with spreadsheet ID and column mappings."""
        self.SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
        self.spreadsheet_id = spreadsheet_id
        self.columns = columns
        self.column_reverse = {v: k for k, v in columns.items()}
        self.service = self._authenticate()

    def _authenticate(self):
        """Handles Google Sheets API authentication using service account."""
        credentials = service_account.Credentials.from_service_account_file(
            'token.json', 
            scopes=self.SCOPES
        )
        return build('sheets', 'v4', credentials=credentials, cache_discovery=False)

    def get_row(
        self, column_name: str, search_value: Any
    ) -> Optional[Tuple[int, Dict[str, Any]]]:
        """Get row by searching for a value in a specific column."""
        if column_name not in self.column_reverse:
            raise ValueError(
                f"Column {column_name} not found in column mappings"
            )

        column_letter = self.column_reverse[column_name]
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="A1:Z")
            .execute()
        )

        values = result.get("values", [])
        for row_num, row in enumerate(values, 1):
            col_index = ord(column_letter) - ord("A")
            if len(row) > col_index and row[col_index] == search_value:
                row_data = {
                    col_name: row[ord(col_letter) - ord("A")]
                    for col_letter, col_name in self.columns.items()
                    if ord(col_letter) - ord("A") < len(row)
                }
                return row_num, row_data

        return None

    def update(self, row_number: int, data: Dict[str, Any]) -> None:
        """Update specific cells in a row using column mappings."""
        updates = []
        for col_name, value in data.items():
            if col_name not in self.column_reverse:
                raise ValueError(
                    f"Column {col_name} not found in column mappings"
                )
            col_letter = self.column_reverse[col_name]
            cell = f"{col_letter}{row_number}"
            updates.append({"range": cell, "values": [[value]]})

        body = {"valueInputOption": "RAW", "data": updates}

        self.service.spreadsheets().values().batchUpdate(
            spreadsheetId=self.spreadsheet_id, body=body
        ).execute()

    def append(self, data: Dict[str, Any]) -> None:
        """Append a new row using column mappings."""
        max_col = max(ord(col) - ord("A") for col in self.columns.keys())
        row = [""] * (max_col + 1)

        for col_name, value in data.items():
            if col_name not in self.column_reverse:
                raise ValueError(
                    f"Column {col_name} not found in column mappings"
                )
            col_index = ord(self.column_reverse[col_name]) - ord("A")
            row[col_index] = value

        body = {"values": [row]}

        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range="A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()
