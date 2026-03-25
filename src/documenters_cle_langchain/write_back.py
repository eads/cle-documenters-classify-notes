"""write_back.py — Classified notes tab output for the write_back node.

Writes one new tab per run to the Google Sheet. Tab name: ``classified-notes-YYYY-MM-DD``.
One row per processed follow-up question.

Column schema:
  Agent-filled (read-only for reporters):
    Meeting date, Meeting body, Source question, Sub-topic, Topic,
    Retrieved similar themes, Confidence, Needs review,
    Question type, Question type: low confidence
  Reporter decision columns (blank on write):
    Decision, Corrected sub-topic, Question type override,
    Proposed new question type, Notes

``Needs review`` is "yes" for rows with merge_confidence below the review
threshold. Reporters filter on this column to triage flagged classifications.

``Retrieved similar themes`` is formatted as human-readable numbered lines
(not raw JSON) — this is the column that gives reporters enough context to
make a Rename decision without reading documentation.
"""
from __future__ import annotations

import logging
from typing import Any

from .classify_themes import ClassifiedTheme
from .ingest import IngestedDoc

log = logging.getLogger(__name__)

CLASSIFIED_NOTES_TAB_PREFIX = "classified-notes-"

# Ordered column headers exactly as written to the Sheets tab.
COLUMNS = [
    # --- agent-filled ---
    "Meeting date",
    "Meeting body",
    "Source question",
    "Sub-topic",
    "Topic",
    "Retrieved similar themes",
    "Confidence",
    "Needs review",
    "Question type",
    "Question type: low confidence",
    # --- reporter decision columns (blank on write) ---
    "Decision",
    "Corrected sub-topic",
    "Question type override",
    "Proposed new question type",
    "Notes",
]


def classified_notes_tab_name(run_date: str) -> str:
    """Return the tab name for a given run date."""
    return f"{CLASSIFIED_NOTES_TAB_PREFIX}{run_date}"


# ---------------------------------------------------------------------------
# Row construction — pure functions, testable without credentials
# ---------------------------------------------------------------------------


def _format_retrieved_context(retrieved_context: list[dict]) -> str:
    """Format retrieved similar themes as human-readable numbered lines.

    Caps at 3 themes (matching the architecture spec of 2–3 per question).
    Returns empty string when no context was retrieved (cold start).
    """
    if not retrieved_context:
        return ""
    lines = []
    for i, t in enumerate(retrieved_context[:3], 1):
        lines.append(f"{i}. {t['sub_topic']} — {t['description']} ({t['topic']})")
    return "\n".join(lines)


def build_classified_notes_rows(
    classified_themes: list[ClassifiedTheme],
    ingested_docs: list[IngestedDoc],
) -> list[list]:
    """Build the full row list (header + data) for the classified notes tab.

    Joins each ClassifiedTheme to its source IngestedDoc on doc_id to populate
    meeting date and body. If a doc_id is not found (shouldn't happen in normal
    operation), meeting fields are left blank rather than raising.

    Args:
        classified_themes: all ClassifiedTheme results from classify_themes node.
        ingested_docs: all IngestedDocs from the ingest node.

    Returns:
        ``[header_row, data_row, ...]``. Returns ``[header_row]`` when
        classified_themes is empty.
    """
    doc_lookup: dict[str, IngestedDoc] = {d["doc_id"]: d for d in ingested_docs}

    rows: list[list] = [COLUMNS]
    for theme in classified_themes:
        doc = doc_lookup.get(theme.doc_id)
        meeting_date = ""
        meeting_body = ""
        if doc:
            meeting_date = doc["date"] or doc["date_raw"] or ""
            meeting_body = doc["agency"] or ""

        qt_low_confidence = (
            "yes"
            if (theme.question_type_low_confidence or theme.proposed_new_question_type)
            else ""
        )

        rows.append([
            meeting_date,
            meeting_body,
            theme.source_question,
            theme.sub_topic,
            theme.topic,
            _format_retrieved_context(theme.retrieved_context),
            round(theme.merge_confidence, 2),
            "yes" if theme.needs_review else "",
            theme.question_type or "",
            qt_low_confidence,
            "",  # Decision
            "",  # Corrected sub-topic
            "",  # Question type override
            "",  # Proposed new question type
            "",  # Notes
        ])

    return rows


# ---------------------------------------------------------------------------
# Sheets I/O
# ---------------------------------------------------------------------------


def write_classified_notes(
    classified_themes: list[ClassifiedTheme],
    ingested_docs: list[IngestedDoc],
    sheets: Any,
    sheet_id: str,
    run_date: str,
) -> str:
    """Write the classified notes tab for this run.

    Creates a new tab named ``classified-notes-{run_date}``. Writes header row
    plus one data row per classified theme. Nothing is overwritten — each run
    gets its own tab.

    Args:
        classified_themes: all ClassifiedTheme results from this run.
        ingested_docs: all IngestedDocs from this run (for date/body lookup).
        sheets: Google Sheets API client (from ``build_sheets_client``).
        sheet_id: the ID of the target spreadsheet.
        run_date: ISO date string (YYYY-MM-DD) used for the tab name.

    Returns:
        The tab name that was created.
    """
    tab = classified_notes_tab_name(run_date)

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
    ).execute()
    log.info("write_back: created tab '%s'", tab)

    rows = build_classified_notes_rows(classified_themes, ingested_docs)
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    data_rows = len(rows) - 1
    log.info(
        "write_back: wrote %d classified notes row%s to '%s'",
        data_rows,
        "s" if data_rows != 1 else "",
        tab,
    )
    return tab
