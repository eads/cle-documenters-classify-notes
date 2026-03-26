"""write_back.py — Classified notes tab output for the write_back node.

Writes one new tab per run to the Google Sheet. Tab name: ``classified-notes-YYYY-MM-DD``.
One row per processed follow-up question.

Column schema (left to right as written to the sheet):
  Agent-filled (read-only for reporters):
    Meeting date, Meeting body, Source question, Topic, Sub-topic,
    Sub-topic confidence, Question type, Question type confidence
  Reporter decision columns (blank on write):
    Decision, Corrected sub-topic, Proposed new question type,
    Question type override, Notes
  Triage / reference (end of row):
    Needs review, GDoc URL, Retrieved similar themes

``Needs review`` is "yes" for rows with merge_confidence below the review
threshold. Reporters filter on this column to triage flagged rows.

``Sub-topic confidence`` and ``Question type confidence`` are floats (0.0–1.0,
rounded to 2 decimal places). Numeric scores let reporters sort and filter by
degree of certainty rather than relying on a boolean flag.

``Retrieved similar themes`` is formatted as human-readable numbered lines
(not raw JSON) — this is the column that gives reporters enough context to
make a Rename decision without reading documentation.
"""
from __future__ import annotations

import logging
from typing import Any

from .classify_themes import ClassifiedTheme
from .ingest import IngestedDoc
from .theme_library import ThemeRecord

log = logging.getLogger(__name__)

CLASSIFIED_NOTES_TAB_PREFIX = "classified-notes-"

# Ordered column headers exactly as written to the Sheets tab.
COLUMNS = [
    # --- agent-filled ---
    "Meeting date",
    "Meeting body",
    "Source question",
    "Topic",
    "Sub-topic",
    "Sub-topic description",
    "Sub-topic confidence",
    # --- reporter decision columns (blank on write) ---
    "Decision",
    "Corrected sub-topic",
    "Question type",
    "Proposed new question type",
    "Question type override",
    "Question type confidence",
    "Notes",
    # --- triage / reference ---
    "Needs review",
    "GDoc URL",
    "Retrieved similar themes",
]

# Pixel widths for each COLUMNS entry (same order).
_COLUMN_WIDTHS = [
    80,   # Meeting date
    150,  # Meeting body
    300,  # Source question
    130,  # Topic
    150,  # Sub-topic
    200,  # Sub-topic description
    80,   # Sub-topic confidence
    150,  # Decision
    150,  # Corrected sub-topic
    150,  # Question type
    120,  # Proposed new question type
    150,  # Question type override
    80,   # Question type confidence
    120,  # Notes
    80,   # Needs review
    120,  # GDoc URL
    400,  # Retrieved similar themes
]

# Columns that get text-wrap enabled (long free-text content).
_WRAP_COLUMNS = [
    COLUMNS.index("Source question"),
    COLUMNS.index("Sub-topic"),
    COLUMNS.index("Sub-topic description"),
    COLUMNS.index("Retrieved similar themes"),
]


def next_classified_notes_tab_name(run_date: str, existing_titles: list[str]) -> str:
    """Return the next versioned tab name for a given run date.

    Format: ``classified-notes-YYYY-MM-DD-NNN``.

    Counts existing tabs that match the ``classified-notes-{run_date}-``
    prefix and increments. First run of the day → 001, second → 002, etc.
    Tabs from other dates or with other prefixes are ignored.
    """
    prefix = f"{CLASSIFIED_NOTES_TAB_PREFIX}{run_date}-"
    n = sum(1 for t in existing_titles if t.startswith(prefix)) + 1
    return f"{prefix}{n:03d}"


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
        gdoc_url = ""
        if doc:
            meeting_date = doc["date"] or doc["date_raw"] or ""
            meeting_body = doc["agency"] or ""
            gdoc_url = doc["web_url"] or ""

        rows.append([
            meeting_date,                                   # Meeting date
            meeting_body,                                   # Meeting body
            theme.source_question,                          # Source question
            theme.topic,                                    # Topic
            theme.sub_topic,                                # Sub-topic
            theme.description or "",                        # Sub-topic description
            round(theme.merge_confidence, 2),               # Sub-topic confidence
            "",                                             # Decision
            "",                                             # Corrected sub-topic
            theme.question_type or "",                      # Question type
            "",                                             # Proposed new question type
            "",                                             # Question type override
            round(theme.question_type_confidence, 2),       # Question type confidence
            "",                                             # Notes
            "yes" if theme.needs_review else "",            # Needs review
            gdoc_url,                                       # GDoc URL
            _format_retrieved_context(theme.retrieved_context),  # Retrieved similar themes
        ])

    return rows


# ---------------------------------------------------------------------------
# Sheet formatting
# ---------------------------------------------------------------------------


def format_tab(
    sheets: Any,
    sheet_id: str,
    tab_sheet_id: int,
    column_widths: list[int],
    wrap_columns: list[int],
) -> None:
    """Apply formatting to a newly created tab in a single batchUpdate call.

    Applies frozen header row, bold header row, per-column pixel widths, and
    text-wrap on specified columns.  All formatting is batched into a single
    API call to minimise latency.

    Args:
        sheets: Google Sheets API client.
        sheet_id: spreadsheet ID.
        tab_sheet_id: integer sheetId of the new tab (from addSheet response).
        column_widths: pixel width for each column, in order.
        wrap_columns: zero-based column indices that should wrap text.
    """
    requests: list[dict] = []

    # Freeze the header row.
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": tab_sheet_id,
                "gridProperties": {"frozenRowCount": 1},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Bold and wrap the header row.
    requests.append({
        "repeatCell": {
            "range": {"sheetId": tab_sheet_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "wrapStrategy": "WRAP"}},
            "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.wrapStrategy",
        }
    })

    # Set column widths.
    for col_idx, width_px in enumerate(column_widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": tab_sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": col_idx,
                    "endIndex": col_idx + 1,
                },
                "properties": {"pixelSize": width_px},
                "fields": "pixelSize",
            }
        })

    # Wrap text on long-content columns.
    for col_idx in wrap_columns:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": tab_sheet_id,
                    "startColumnIndex": col_idx,
                    "endColumnIndex": col_idx + 1,
                },
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat.wrapStrategy",
            }
        })

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": requests},
    ).execute()


# ---------------------------------------------------------------------------
# Library description enrichment
# ---------------------------------------------------------------------------


def enrich_library_descriptions(
    library: list[ThemeRecord],
    classified_themes: list[ClassifiedTheme],
) -> None:
    """Seed missing descriptions in library records from the current run's classified themes.

    Mutates records in place. Only updates records whose description is currently empty.

    This handles the "original sin" case where themes were created before the
    classified-notes tab had a Sub-topic description column, so all prior
    ReviewDecision rows carry description="" and apply_decisions can never seed
    them.  By enriching here — after decisions are applied but before the
    theme-overview tab is written — we ensure descriptions appear in the
    library on the same run that first produces a matching classified theme,
    rather than requiring an additional run.

    Descriptions are LLM-generated metadata, not human approval decisions, so
    there is no reason to gate them behind the 2-run review cycle.
    """
    if not classified_themes:
        return
    desc_by_subtopic = {ct.sub_topic: ct.description for ct in classified_themes if ct.description}
    for record in library:
        if not record.description:
            record.description = desc_by_subtopic.get(record.sub_topic, "")


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
    metadata = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_titles = [s["properties"]["title"] for s in metadata.get("sheets", [])]
    tab = next_classified_notes_tab_name(run_date, existing_titles)

    add_response = sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
    ).execute()
    tab_sheet_id = add_response["replies"][0]["addSheet"]["properties"]["sheetId"]
    log.info("write_back: created tab '%s'", tab)

    rows = build_classified_notes_rows(classified_themes, ingested_docs)
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    format_tab(sheets, sheet_id, tab_sheet_id, _COLUMN_WIDTHS, _WRAP_COLUMNS)

    data_rows = len(rows) - 1
    log.info(
        "write_back: wrote %d classified notes row%s to '%s'",
        data_rows,
        "s" if data_rows != 1 else "",
        tab,
    )
    return tab
