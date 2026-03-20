"""gsheets.py — create a new Google Sheet in a Drive folder and upload results."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def _clients(credentials_file: str | Path):
    creds = service_account.Credentials.from_service_account_file(
        str(credentials_file), scopes=_SCOPES
    )
    sheets = build("sheets", "v4", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return sheets, drive


def upload_results(
    results: list,
    folder_id: str,
    title: str,
    credentials_file: str | Path | None = None,
) -> str:
    """Create a new Google Sheet in *folder_id*, write *results* to it, and return the URL.

    Args:
        results: list of PipelineDoc (from pipeline.py)
        folder_id: Drive folder ID to place the sheet in
        title: spreadsheet title (shown in Drive)
        credentials_file: path to service account JSON; falls back to
            GOOGLE_APPLICATION_CREDENTIALS env var
    """
    if credentials_file is None:
        credentials_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_file:
        raise RuntimeError(
            "Provide credentials_file or set GOOGLE_APPLICATION_CREDENTIALS."
        )

    sheets_client, drive_client = _clients(credentials_file)

    # Create the spreadsheet (lands in service account's root)
    spreadsheet = (
        sheets_client.spreadsheets()
        .create(body={"properties": {"title": title}})
        .execute()
    )
    spreadsheet_id = spreadsheet["spreadsheetId"]
    url = spreadsheet["spreadsheetUrl"]
    log.info("created spreadsheet: %s (%s)", title, url)

    # Write data
    rows = _build_rows(results)
    if rows:
        sheets_client.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Sheet1",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()
        log.info("wrote %d rows to sheet", len(rows) - 1)

    # Move into the target Drive folder
    file_meta = drive_client.files().get(
        fileId=spreadsheet_id, fields="parents"
    ).execute()
    current_parents = ",".join(file_meta.get("parents", []))
    drive_client.files().update(
        fileId=spreadsheet_id,
        addParents=folder_id,
        removeParents=current_parents,
        fields="id, parents",
        supportsAllDrives=True,
    ).execute()
    log.info("moved sheet to folder %s", folder_id)

    return url


def _score_label(score: float) -> str:
    from .classifiers import AMBIGUOUS_LO, AMBIGUOUS_HI
    if score > AMBIGUOUS_HI:
        return "certain"
    if score < AMBIGUOUS_LO:
        return "unlikely"
    return "ambiguous"


def _build_rows(results: list) -> list[list]:
    if not results:
        return []
    slugs = list(results[0].topics.keys())
    category_cols = []
    for s in slugs:
        category_cols += [f"{s}_score", f"{s}_label", f"{s}_identified"]
    header = ["web_url", "name", "date", "agency", "model_used"] + category_cols
    rows = [header]
    for r in results:
        row = [r.web_url, r.name, r.date or r.date_raw, r.agency, r.model_used]
        for s in slugs:
            cat = r.topics[s]
            row.append(cat["score"])
            row.append(_score_label(cat["score"]))
            row.append("; ".join(cat.get("identified", [])))
        rows.append(row)
    return rows
