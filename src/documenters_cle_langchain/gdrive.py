from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .text_extract import extract_text

log = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]

# Resolves all suggestions to their accepted state before extracting text.
_SUGGESTIONS_MODE = "PREVIEW_SUGGESTIONS_ACCEPTED"


@dataclass(slots=True, frozen=True)
class DriveDocMeta:
    gdoc_id: str
    name: str
    web_url: str
    folder_id: str          # immediate parent folder ID
    folder_path: str        # slash-joined chain of folder names from the root you queried
    modified_time: str      # ISO 8601 from Drive API


@dataclass(slots=True, frozen=True)
class FetchedDoc:
    gdoc_id: str
    name: str
    web_url: str
    folder_id: str
    folder_path: str
    modified_time: str
    text: str
    text_checksum: str  # SHA256 of normalized text for deduplication


class GoogleDocsClient:
    """Thin wrapper around Drive v3 + Docs v1 APIs.

    Supports two auth modes:
    - API key (simplest — works for publicly shared folders/docs)
    - Service account (needed for private/org-restricted content)
    """

    def __init__(self, *, api_key: str | None = None, credentials_file: str | Path | None = None) -> None:
        if api_key and not credentials_file:
            self._drive = build("drive", "v3", developerKey=api_key)
            self._docs = None  # Docs API requires OAuth/service account
            log.warning(
                "API key only — will use Drive export for text (no suggestion resolution). "
                "Set GOOGLE_APPLICATION_CREDENTIALS for full Docs API access."
            )
        elif credentials_file:
            creds = service_account.Credentials.from_service_account_file(
                str(credentials_file), scopes=_SCOPES
            )
            self._drive = build("drive", "v3", credentials=creds)
            self._docs = build("docs", "v1", credentials=creds)
        else:
            raise ValueError("Provide either api_key or credentials_file.")

    @classmethod
    def from_env(cls) -> "GoogleDocsClient":
        """Construct from environment variables.

        Checks GOOGLE_API_KEY first (public folders), then falls back to
        GOOGLE_APPLICATION_CREDENTIALS (service account JSON path).
        """
        sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if sa_path:
            return cls(credentials_file=sa_path)
        api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            return cls(api_key=api_key)
        raise RuntimeError(
            "Set GOOGLE_APPLICATION_CREDENTIALS (service account, full access) or "
            "GOOGLE_API_KEY (public folders only, no suggestion resolution)."
        )

    def list_folder_docs(
        self,
        folder_id: str,
        year: int | None = None,
        month: str | None = None,
    ) -> list[DriveDocMeta]:
        """Return metadata for all Google Docs under *folder_id*, recursing into subfolders.

        year and month prune the traversal early — e.g. year=2026, month="March"
        will only enter the 2026/March subtree.
        """
        results: list[DriveDocMeta] = []
        self._collect_docs(
            folder_id,
            folder_path="",
            results=results,
            visited=set(),
            year=year,
            month=month,
        )
        return results


def _checksum(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode()).hexdigest()

    def _collect_docs(
        self,
        folder_id: str,
        folder_path: str,
        results: list[DriveDocMeta],
        visited: set[str],
        year: int | None,
        month: str | None,
    ) -> None:
        if folder_id in visited:
            return
        visited.add(folder_id)

        # depth 0 = year folders, depth 1 = month folders, depth 2 = date folders
        depth = len(folder_path.split("/")) if folder_path else 0

        query = (
            f"'{folder_id}' in parents"
            " and trashed=false"
            " and (mimeType='application/vnd.google-apps.document'"
            "  or mimeType='application/vnd.google-apps.folder')"
        )
        page_token: str | None = None

        while True:
            resp = (
                self._drive.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, mimeType, webViewLink, modifiedTime)",
                    pageToken=page_token,
                    pageSize=100,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            for f in resp.get("files", []):
                mime = f["mimeType"]
                name = f["name"]
                if mime == "application/vnd.google-apps.document":
                    if depth == 0 and year:
                        log.info("  skipping root-level doc (not in year folder): %s", name)
                        continue
                    log.info("  found doc: %s (%s)", name, folder_path or "/")
                    results.append(
                        DriveDocMeta(
                            gdoc_id=f["id"],
                            name=name,
                            web_url=f.get("webViewLink", ""),
                            folder_id=folder_id,
                            folder_path=folder_path,
                            modified_time=f.get("modifiedTime", ""),
                        )
                    )
                elif mime == "application/vnd.google-apps.folder":
                    child_path = f"{folder_path}/{name}" if folder_path else name
                    if depth == 0 and year and name != str(year):
                        log.info("skipping year folder: %s", name)
                        continue
                    if depth == 1 and month and name.lower() != month.lower():
                        log.info("skipping month folder: %s", name)
                        continue
                    log.info("entering folder: %s", child_path)
                    self._collect_docs(f["id"], child_path, results, visited, year=year, month=month)

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    def fetch_doc_text(self, gdoc_id: str) -> str:
        """Fetch document content.

        Uses the Docs API with suggestions accepted when a service account is
        available. Falls back to Drive plain-text export (no suggestion
        resolution) when only an API key is configured.
        """
        if self._docs is not None:
            try:
                doc = (
                    self._docs.documents()
                    .get(documentId=gdoc_id, suggestionsViewMode=_SUGGESTIONS_MODE)
                    .execute()
                )
                return extract_text(doc)
            except HttpError as exc:
                if exc.status_code == 403:
                    log.warning(
                        "Cannot access suggestions for %s, fetching without: %s",
                        gdoc_id, exc.reason,
                    )
                    doc = (
                        self._docs.documents()
                        .get(documentId=gdoc_id)
                        .execute()
                    )
                    return extract_text(doc)
                raise

        # API-key fallback: Drive export as plain text
        content = (
            self._drive.files()
            .export(fileId=gdoc_id, mimeType="text/plain")
            .execute()
        )
        return content.decode("utf-8") if isinstance(content, bytes) else content

    def fetch_folder(
        self,
        folder_id: str,
        year: int | None = None,
        month: str | None = None,
    ) -> tuple[list[FetchedDoc], list[tuple[DriveDocMeta, str]]]:
        """Fetch all docs in a folder, optionally filtered by year and month name.

        Returns (successes, failures) where failures is a list of
        (DriveDocMeta, error_message) pairs.
        """
        metas = self.list_folder_docs(folder_id, year=year, month=month)
        successes: list[FetchedDoc] = []
        failures: list[tuple[DriveDocMeta, str]] = []

        log.info("fetching text for %d docs", len(metas))
        for i, meta in enumerate(metas, 1):
            try:
                log.info("[%d/%d] fetching: %s", i, len(metas), meta.name)
                text = self.fetch_doc_text(meta.gdoc_id)
                successes.append(
                    FetchedDoc(
                        gdoc_id=meta.gdoc_id,
                        name=meta.name,
                        web_url=meta.web_url,
                        folder_id=meta.folder_id,
                        folder_path=meta.folder_path,
                        modified_time=meta.modified_time,
                        text=text,
                        text_checksum=_checksum(text),
                    )
                )
            except HttpError as exc:
                failures.append((meta, str(exc)))

        return successes, failures
