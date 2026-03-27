"""theme_library.py — Theme Library schema and Google Sheets persistence.

The Theme Library is the dimension table in the two-tab Sheets model:
  - Theme library tab  (this module)  — one row per confirmed sub-topic theme
  - Classified notes tab (write_back) — one row per follow-up question (fact table)

They join on ``sub_topic``. Source passages are NOT stored exhaustively here;
the classified notes tabs are the canonical record. ThemeRecord carries up to
3 representative passages for inline retrieval display only.

Tab naming: ``theme-overview-YYYY-MM-DD``. Each run writes a new versioned tab;
nothing is ever overwritten. The next run reads it as a base cache, then applies
new decisions from the classified notes tab on top. Humans read this tab for
reference but do not edit it — it is agent-owned and will be regenerated.
"""
from __future__ import annotations

import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Taxonomy enums
# ---------------------------------------------------------------------------

THEME_TAB_PREFIX = "themes-"
_SEP = " ||| "
_MAX_PASSAGES = 3


class Topic(str, Enum):
    """National Documenters topic taxonomy — top-level rollup for sub-topics."""
    AGRICULTURE = "AGRICULTURE"
    ARTS = "ARTS"
    BUDGET = "BUDGET"
    CENSUS_2020 = "CENSUS 2020"
    CRIMINAL_JUSTICE = "CRIMINAL JUSTICE"
    DEVELOPMENT = "DEVELOPMENT"
    EDUCATION = "EDUCATION"
    ELECTIONS = "ELECTIONS"
    ENVIRONMENT = "ENVIRONMENT"
    FINANCE = "FINANCE"
    HEALTH = "HEALTH"
    HOUSING = "HOUSING"
    LABOR = "LABOR"
    LIBRARIES = "LIBRARIES"
    PARKS = "PARKS"
    POLITICS = "POLITICS"
    PUBLIC_SAFETY = "PUBLIC SAFETY"
    TRANSPORTATION = "TRANSPORTATION"
    URBAN_ANIMALS = "URBAN ANIMALS"
    UTILITIES = "UTILITIES"


class QuestionType(str, Enum):
    """Epistemic posture taxonomy for follow-up questions."""
    KNOWLEDGE_GAP = "knowledge_gap"
    PROCESS_CONFUSION = "process_confusion"
    SKEPTICISM = "skepticism"
    ACCOUNTABILITY = "accountability"
    CONTINUITY = "continuity"


# ---------------------------------------------------------------------------
# ThemeRecord schema
# ---------------------------------------------------------------------------

# Ordered column headers exactly as written to / read from the Sheets tab.
COLUMNS = [
    "Sub-topic",
    "Description",
    "Included in topics",
    "Occurrences",
    "Knowledge gap",
    "Process confusion",
    "Skepticism",
    "Accountability",
    "Continuity",
    "Representative passages",
]

# Pixel widths for each COLUMNS entry (same order).
_COLUMN_WIDTHS = [
    150,  # Sub-topic
    300,  # Description
    150,  # Included in topics
    80,   # Occurrences
    80,   # Knowledge gap
    80,   # Process confusion
    80,   # Skepticism
    80,   # Accountability
    80,   # Continuity
    400,  # Representative passages
]

# Columns that get text-wrap enabled.
_WRAP_COLUMNS = [
    COLUMNS.index("Description"),
    COLUMNS.index("Representative passages"),
]


class ThemeRecord(BaseModel):
    """A confirmed sub-topic theme in the Theme Library.

    The Theme Library is the dimension table. Source questions (passages) live
    in the classified notes tabs (fact table) and join here on ``sub_topic``.
    ``representative_passages`` holds up to 3 examples for retrieval display —
    not the full corpus.

    ``topics`` accumulates all national taxonomy topics seen for this sub-topic
    across runs.  Cross-cutting sub-topics (e.g. "transparency") will appear
    under multiple topics; domain-specific ones will have a single entry.
    """
    sub_topic: str
    description: str = ""   # empty when theme is bootstrapped from a decision row
    topics: list[Topic] = Field(default_factory=list)
    occurrence_count: int = 0
    # Question type distribution — denormalized rollup counts
    knowledge_gap_count: int = 0
    process_confusion_count: int = 0
    skepticism_count: int = 0
    accountability_count: int = 0
    continuity_count: int = 0
    # Up to 3 representative source passages for inline retrieval display.
    # Not exhaustive — full history lives in the classified notes tabs.
    representative_passages: list[str] = Field(default_factory=list, max_length=_MAX_PASSAGES)

    def add_passage(self, passage: str) -> None:
        """Add a representative passage if we have fewer than the max."""
        if len(self.representative_passages) < _MAX_PASSAGES:
            if passage not in self.representative_passages:
                self.representative_passages.append(passage)

    def to_row(self) -> list:
        """Serialize to a flat list matching COLUMNS order."""
        return [
            self.sub_topic,
            self.description,
            ", ".join(t.value for t in self.topics),
            self.occurrence_count,
            self.knowledge_gap_count,
            self.process_confusion_count,
            self.skepticism_count,
            self.accountability_count,
            self.continuity_count,
            _SEP.join(self.representative_passages),
        ]

    @classmethod
    def from_row(cls, row: list, headers: list[str]) -> "ThemeRecord":
        """Deserialize from a flat row using header positions.

        Tolerates missing columns (uses defaults) so the schema can evolve
        without breaking reads of older tabs.
        """
        idx = {h: i for i, h in enumerate(headers)}

        def get(col: str, default: Any = "") -> Any:
            i = idx.get(col)
            if i is None or i >= len(row):
                return default
            return row[i]

        def get_int(col: str) -> int:
            try:
                return int(get(col, 0) or 0)
            except (ValueError, TypeError):
                return 0

        passages_raw = get("Representative passages", "")
        passages = [p.strip() for p in passages_raw.split(_SEP) if p.strip()]

        # "Included in topics" is the current column name.  Older tabs wrote a
        # single value under "Topic" — fall back to that for backward compat.
        topics_raw = get("Included in topics", "") or get("Topic", "")
        topic_strings = [t.strip() for t in topics_raw.split(",") if t.strip()]
        topics = [Topic(ts) for ts in topic_strings]   # ValueError → caller skips row

        return cls(
            sub_topic=get("Sub-topic"),
            description=get("Description"),
            topics=topics,
            occurrence_count=get_int("Occurrences"),
            knowledge_gap_count=get_int("Knowledge gap"),
            process_confusion_count=get_int("Process confusion"),
            skepticism_count=get_int("Skepticism"),
            accountability_count=get_int("Accountability"),
            continuity_count=get_int("Continuity"),
            representative_passages=passages[:_MAX_PASSAGES],
        )


# ---------------------------------------------------------------------------
# Tab utilities
# ---------------------------------------------------------------------------

def find_latest_theme_tab(tab_titles: list[str]) -> str | None:
    """Return the most recent theme library tab name, or None if none exist.

    Theme library tabs are named ``theme-library-YYYY-MM-DD``. ISO date
    strings sort lexicographically, so the latest is simply the max.
    """
    theme_tabs = [t for t in tab_titles if t.startswith(THEME_TAB_PREFIX)]
    if not theme_tabs:
        return None
    return max(theme_tabs)


def next_theme_tab_name(
    run_date: str,
    existing_titles: list[str],
    run_name: str = "",
) -> str:
    """Return the next versioned tab name for a given run date.

    Format: ``themes-YYYY-MM-DD-NNN`` or ``themes-YYYY-MM-DD-{name}-NNN``.

    The version counter is date-scoped: all tabs on the same date share the
    same counter regardless of name. First run of the day → 001, second → 002,
    etc. Tab titles are truncated to 100 characters (Google Sheets limit).
    """
    slug = run_name.strip().replace(" ", "-") if run_name.strip() else ""
    date_prefix = f"{THEME_TAB_PREFIX}{run_date}-"
    n = sum(1 for t in existing_titles if t.startswith(date_prefix)) + 1
    name = f"{date_prefix}{slug}-{n:03d}" if slug else f"{date_prefix}{n:03d}"
    return name[:100]


# ---------------------------------------------------------------------------
# Google Sheets API
# ---------------------------------------------------------------------------

def build_sheets_client(
    credentials_file: str | Path | None = None,
    impersonate: str | None = None,
) -> Any:
    """Build a Google Sheets API client from a service account credentials file."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    if credentials_file is None:
        credentials_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_file:
        raise RuntimeError(
            "Provide credentials_file or set GOOGLE_APPLICATION_CREDENTIALS."
        )
    creds = service_account.Credentials.from_service_account_file(
        str(credentials_file),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    if impersonate:
        creds = creds.with_subject(impersonate)
    return build("sheets", "v4", credentials=creds)


def read_theme_library(sheets: Any, sheet_id: str) -> list[ThemeRecord]:
    """Read the most recent theme library tab from a Google Sheet.

    Returns an empty list on cold start (no theme library tab exists yet).

    Args:
        sheets: Google Sheets API client (from ``build_sheets_client``).
        sheet_id: the ID of the target spreadsheet.
    """
    # Get all tab titles.
    metadata = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
    titles = [s["properties"]["title"] for s in metadata.get("sheets", [])]

    tab = find_latest_theme_tab(titles)
    if tab is None:
        log.info("theme library: no existing tab found — cold start")
        return []

    log.info("theme library: reading from tab '%s'", tab)
    result = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"'{tab}'")
        .execute()
    )
    rows = result.get("values", [])
    if len(rows) < 2:
        log.info("theme library: tab '%s' is empty", tab)
        return []

    headers = rows[0]
    records = []
    for row in rows[1:]:
        try:
            records.append(ThemeRecord.from_row(row, headers))
        except Exception as exc:
            log.warning("theme library: skipping malformed row: %s", exc)
    log.info("theme library: loaded %d records from '%s'", len(records), tab)
    return records


def write_theme_library(
    records: list[ThemeRecord],
    sheets: Any,
    sheet_id: str,
    run_date: str,
    run_name: str = "",
) -> str:
    """Write theme library records to a new versioned tab.

    Creates a tab named ``themes-{run_date}-NNN`` or
    ``themes-{run_date}-{run_name}-NNN``. Nothing is overwritten.

    Args:
        records: theme records to write.
        sheets: Google Sheets API client.
        sheet_id: the ID of the target spreadsheet.
        run_date: ISO date string (YYYY-MM-DD) used for the tab name.
        run_name: optional human label (e.g. "bootstrap", "mar-2026").

    Returns:
        The tab name that was created.
    """
    metadata = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_titles = [s["properties"]["title"] for s in metadata.get("sheets", [])]
    tab = next_theme_tab_name(run_date, existing_titles, run_name)

    add_response = sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
    ).execute()
    tab_sheet_id = add_response["replies"][0]["addSheet"]["properties"]["sheetId"]
    log.info("theme library: created tab '%s'", tab)

    rows = [COLUMNS] + [r.to_row() for r in records]
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    from .write_back import format_tab  # deferred — write_back imports theme_library at module level
    format_tab(sheets, sheet_id, tab_sheet_id, _COLUMN_WIDTHS, _WRAP_COLUMNS)

    log.info("theme library: wrote %d records to '%s'", len(records), tab)
    return tab
