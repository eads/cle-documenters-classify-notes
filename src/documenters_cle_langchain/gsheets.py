"""gsheets.py — create a native Google Sheet in Drive and write results to it."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _clients(credentials_file: str | Path, impersonate: str | None = None):
    creds = service_account.Credentials.from_service_account_file(
        str(credentials_file), scopes=_SCOPES
    )
    if impersonate:
        creds = creds.with_subject(impersonate)
    drive = build("drive", "v3", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)
    return drive, sheets


def upload_results(
    results: list[dict],
    folder_id: str,
    title: str,
    credentials_file: str | Path | None = None,
    impersonate: str | None = None,
) -> str:
    """Create a native Google Sheet in *folder_id*, write results to it, and return its URL.

    Creates an empty Sheet via the Drive API (no file upload, no quota consumed),
    then writes rows via the Sheets API.
    """
    if credentials_file is None:
        credentials_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_file:
        raise RuntimeError(
            "Provide credentials_file or set GOOGLE_APPLICATION_CREDENTIALS."
        )

    impersonate = impersonate or os.environ.get("GOOGLE_IMPERSONATE_USER")
    drive, sheets = _clients(credentials_file, impersonate=impersonate)

    # Create an empty native Sheet directly in the target folder — no upload, no quota used.
    resp = (
        drive.files()
        .create(
            body={
                "name": title,
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "parents": [folder_id],
            },
            fields="id, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    spreadsheet_id = resp["id"]
    url = resp["webViewLink"]
    log.info("created sheet '%s': %s", title, url)

    # Write data via Sheets API.
    rows = _build_rows(results)
    if rows:
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Sheet1",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()
        log.info("wrote %d data rows", len(rows) - 1)

    return url


def _score_label(score: float) -> str:
    from .classifiers import AMBIGUOUS_LO, AMBIGUOUS_HI
    if score > AMBIGUOUS_HI:
        return "certain"
    if score < AMBIGUOUS_LO:
        return "unlikely"
    return "ambiguous"


