"""gsheets.py — write classifier results as a new tab in an existing Google Sheet."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


def _sheets_client(credentials_file: str | Path, impersonate: str | None = None):
    creds = service_account.Credentials.from_service_account_file(
        str(credentials_file), scopes=_SCOPES
    )
    if impersonate:
        creds = creds.with_subject(impersonate)
    return build("sheets", "v4", credentials=creds)


def upload_results(
    results: list[dict],
    sheet_id: str,
    tab_title: str,
    credentials_file: str | Path | None = None,
    impersonate: str | None = None,
) -> str:
    """Add a new tab to an existing Google Sheet and write results to it.

    Returns the URL to the sheet.
    """
    if credentials_file is None:
        credentials_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_file:
        raise RuntimeError(
            "Provide credentials_file or set GOOGLE_APPLICATION_CREDENTIALS."
        )

    impersonate = impersonate or os.environ.get("GOOGLE_IMPERSONATE_USER")
    sheets = _sheets_client(credentials_file, impersonate=impersonate)

    # Add a new tab with the run title.
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab_title}}}]},
    ).execute()
    log.info("added tab '%s'", tab_title)

    # Write data.
    rows = _build_rows(results)
    if rows:
        sheets.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{tab_title}'!A1",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()
        log.info("wrote %d data rows to tab '%s'", len(rows) - 1, tab_title)

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    return url


_AMBIGUOUS_LO = 0.3
_AMBIGUOUS_HI = 0.7


def _score_label(score: float) -> str:
    if score > _AMBIGUOUS_HI:
        return "certain"
    if score < _AMBIGUOUS_LO:
        return "unlikely"
    return "ambiguous"


def _build_rows(results: list[dict]) -> list[list]:
    if not results:
        return []
    slugs = list(results[0]["topics"].keys())
    category_cols = []
    for s in slugs:
        category_cols += [f"{s}_score", f"{s}_label", f"{s}_identified"]
    header = ["web_url", "name", "date", "agency", "model_used"] + category_cols
    rows = [header]
    for r in results:
        row = [
            r["web_url"],
            r["name"],
            r.get("date") or r.get("date_raw", ""),
            r["agency"],
            r.get("model_used", ""),
        ]
        for s in slugs:
            cat = r["topics"][s]
            row.append(cat["score"])
            row.append(_score_label(cat["score"]))
            row.append("; ".join(cat.get("identified", [])))
        rows.append(row)
    return rows
