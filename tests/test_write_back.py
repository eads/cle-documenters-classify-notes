"""Tests for write_back.py — classified notes tab construction and Sheets I/O.

Row-building logic is tested directly (pure functions, no credentials).
Sheets API calls are tested with mocks.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from documenters_cle_langchain.classify_themes import ClassifiedTheme
from documenters_cle_langchain.ingest import IngestedDoc
from documenters_cle_langchain.theme_library import ThemeRecord, Topic
from documenters_cle_langchain.write_back import (
    CLASSIFIED_NOTES_TAB_PREFIX,
    COLUMNS,
    _COLUMN_WIDTHS,
    _WRAP_COLUMNS,
    _format_retrieved_context,
    build_classified_notes_rows,
    enrich_library_descriptions,
    format_tab,
    next_classified_notes_tab_name,
    write_classified_notes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HOUSING_SIMILAR = {
    "sub_topic": "Section 8 voucher waitlists",
    "description": "Long waits for housing vouchers",
    "topic": "HOUSING",
    "similarity_score": 0.91,
}

TRANSIT_SIMILAR = {
    "sub_topic": "Bus route frequency cuts",
    "description": "Reduced service on high-ridership routes",
    "topic": "TRANSPORTATION",
    "similarity_score": 0.75,
}


def make_classified_theme(**kwargs) -> ClassifiedTheme:
    defaults = dict(
        doc_id="doc-001",
        source_question="When will the lead pipes in our neighborhood be replaced?",
        sub_topic="lead pipe replacement funding",
        description="Funding gaps for replacing lead service lines.",
        retrieved_context=[HOUSING_SIMILAR],
        decision="new",
        matched_theme=None,
        merge_confidence=0.82,
        merge_reasoning="Distinct from housing voucher issue.",
        needs_review=False,
        question_type="knowledge_gap",
        question_type_confidence=0.88,
        question_type_low_confidence=False,
        proposed_new_question_type=None,
        topic="UTILITIES",
    )
    return ClassifiedTheme(**{**defaults, **kwargs})


def make_ingested_doc(**kwargs) -> IngestedDoc:
    defaults: IngestedDoc = {  # type: ignore[assignment]
        "doc_id": "doc-001",
        "name": "City Council 2026-02-10",
        "web_url": "https://example.com/doc-001",
        "folder_path": "2026/02",
        "modified_time": "2026-02-10T18:00:00Z",
        "meeting_name": "Cleveland City Council",
        "documenter_name": "Jane Reporter",
        "agency": "Cleveland City Council",
        "date": "2026-02-10",
        "date_raw": "February 10, 2026",
        "documenters_url": "https://documenters.org/events/123",
        "summary": "Council discussed infrastructure.",
        "follow_up_questions": ["When will the lead pipes be replaced?"],
        "notes": "Long meeting.",
        "single_signal": "infrastructure",
        "extraction_confidence": 0.95,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Tab naming
# ---------------------------------------------------------------------------

def test_tab_name_first_run():
    assert next_classified_notes_tab_name("2026-02-10", []) == "classified-notes-2026-02-10-001"


def test_tab_name_second_run():
    existing = ["classified-notes-2026-02-10-001"]
    assert next_classified_notes_tab_name("2026-02-10", existing) == "classified-notes-2026-02-10-002"


def test_tab_name_ignores_other_dates():
    existing = ["classified-notes-2026-02-09-001", "classified-notes-2026-02-09-002"]
    assert next_classified_notes_tab_name("2026-02-10", existing) == "classified-notes-2026-02-10-001"


def test_tab_name_ignores_other_prefixes():
    existing = ["theme-overview-2026-02-10-001", "Sheet1"]
    assert next_classified_notes_tab_name("2026-02-10", existing) == "classified-notes-2026-02-10-001"


def test_tab_name_prefix():
    assert next_classified_notes_tab_name("2026-02-10", []).startswith(CLASSIFIED_NOTES_TAB_PREFIX)


# ---------------------------------------------------------------------------
# Column schema
# ---------------------------------------------------------------------------

def test_column_count():
    assert len(COLUMNS) == 19


def test_column_headers_match_spec():
    assert COLUMNS == [
        "Meeting date",
        "Meeting body",
        "Source question",
        "Topic",
        "Sub-topic",
        "Sub-topic confidence",
        "Question type",
        "Question type confidence",
        "Sub-topic decision",
        "Corrected sub-topic",
        "Topic decision",
        "Corrected topic",
        "Question type decision",
        "Corrected question type",
        "Notes",
        "Needs review",
        "GDoc URL",
        "Sub-topic description",
        "Retrieved similar themes",
    ]


# ---------------------------------------------------------------------------
# _format_retrieved_context
# ---------------------------------------------------------------------------

def test_format_retrieved_context_empty():
    assert _format_retrieved_context([]) == ""


def test_format_retrieved_context_single():
    result = _format_retrieved_context([HOUSING_SIMILAR])
    assert "Section 8 voucher waitlists" in result
    assert "Long waits for housing vouchers" in result
    assert "HOUSING" in result
    assert result.startswith("1.")


def test_format_retrieved_context_multiple():
    result = _format_retrieved_context([HOUSING_SIMILAR, TRANSIT_SIMILAR])
    assert "1." in result
    assert "2." in result
    assert "Section 8 voucher waitlists" in result
    assert "Bus route frequency cuts" in result


def test_format_retrieved_context_caps_at_three():
    themes = [HOUSING_SIMILAR, TRANSIT_SIMILAR, HOUSING_SIMILAR, TRANSIT_SIMILAR]
    result = _format_retrieved_context(themes)
    assert "4." not in result
    assert "3." in result


# ---------------------------------------------------------------------------
# build_classified_notes_rows
# ---------------------------------------------------------------------------

def test_empty_classified_themes_produces_headers_only():
    rows = build_classified_notes_rows([], [])
    assert rows == [COLUMNS]


def test_row_count_matches_themes():
    themes = [make_classified_theme(), make_classified_theme(doc_id="doc-002")]
    docs = [make_ingested_doc(), make_ingested_doc(doc_id="doc-002")]
    rows = build_classified_notes_rows(themes, docs)
    assert len(rows) == 3  # header + 2 data rows


def test_header_row_is_columns():
    rows = build_classified_notes_rows([make_classified_theme()], [make_ingested_doc()])
    assert rows[0] == COLUMNS


def test_data_row_meeting_date_from_ingested_doc():
    rows = build_classified_notes_rows([make_classified_theme()], [make_ingested_doc()])
    row = rows[1]
    assert row[COLUMNS.index("Meeting date")] == "2026-02-10"


def test_data_row_meeting_body_from_ingested_doc():
    rows = build_classified_notes_rows([make_classified_theme()], [make_ingested_doc()])
    row = rows[1]
    assert row[COLUMNS.index("Meeting body")] == "Cleveland City Council"


def test_data_row_gdoc_url_from_ingested_doc():
    rows = build_classified_notes_rows([make_classified_theme()], [make_ingested_doc()])
    row = rows[1]
    assert row[COLUMNS.index("GDoc URL")] == "https://example.com/doc-001"


def test_data_row_source_question():
    rows = build_classified_notes_rows([make_classified_theme()], [make_ingested_doc()])
    row = rows[1]
    assert "lead pipes" in row[COLUMNS.index("Source question")]


def test_data_row_sub_topic():
    rows = build_classified_notes_rows([make_classified_theme()], [make_ingested_doc()])
    row = rows[1]
    assert row[COLUMNS.index("Sub-topic")] == "lead pipe replacement funding"


def test_data_row_sub_topic_description():
    rows = build_classified_notes_rows([make_classified_theme()], [make_ingested_doc()])
    row = rows[1]
    assert row[COLUMNS.index("Sub-topic description")] == "Funding gaps for replacing lead service lines."


def test_data_row_sub_topic_description_empty_string():
    theme = make_classified_theme(description="")
    rows = build_classified_notes_rows([theme], [make_ingested_doc()])
    assert rows[1][COLUMNS.index("Sub-topic description")] == ""


def test_data_row_topic():
    rows = build_classified_notes_rows([make_classified_theme()], [make_ingested_doc()])
    row = rows[1]
    assert row[COLUMNS.index("Topic")] == "UTILITIES"


def test_data_row_retrieved_themes_human_readable():
    theme = make_classified_theme(retrieved_context=[HOUSING_SIMILAR])
    rows = build_classified_notes_rows([theme], [make_ingested_doc()])
    cell = rows[1][COLUMNS.index("Retrieved similar themes")]
    assert "Section 8 voucher waitlists" in cell
    assert "Long waits for housing vouchers" in cell
    assert "HOUSING" in cell


def test_data_row_sub_topic_confidence_numeric():
    rows = build_classified_notes_rows([make_classified_theme(merge_confidence=0.823)], [make_ingested_doc()])
    assert rows[1][COLUMNS.index("Sub-topic confidence")] == 0.82


def test_needs_review_false_row_has_empty_flag():
    theme = make_classified_theme(needs_review=False)
    rows = build_classified_notes_rows([theme], [make_ingested_doc()])
    assert rows[1][COLUMNS.index("Needs review")] == ""


def test_needs_review_true_row_has_yes_flag():
    theme = make_classified_theme(needs_review=True, merge_confidence=0.25)
    rows = build_classified_notes_rows([theme], [make_ingested_doc()])
    assert rows[1][COLUMNS.index("Needs review")] == "yes"


def test_question_type_populated():
    rows = build_classified_notes_rows([make_classified_theme()], [make_ingested_doc()])
    assert rows[1][COLUMNS.index("Question type")] == "knowledge_gap"


def test_question_type_none_becomes_empty_string():
    theme = make_classified_theme(question_type=None)
    rows = build_classified_notes_rows([theme], [make_ingested_doc()])
    assert rows[1][COLUMNS.index("Question type")] == ""


def test_qt_confidence_is_numeric():
    theme = make_classified_theme(question_type_confidence=0.77)
    rows = build_classified_notes_rows([theme], [make_ingested_doc()])
    assert rows[1][COLUMNS.index("Question type confidence")] == 0.77


def test_qt_confidence_rounds_to_two_decimal_places():
    theme = make_classified_theme(question_type_confidence=0.876)
    rows = build_classified_notes_rows([theme], [make_ingested_doc()])
    assert rows[1][COLUMNS.index("Question type confidence")] == 0.88


def test_reporter_decision_columns_are_blank():
    rows = build_classified_notes_rows([make_classified_theme()], [make_ingested_doc()])
    row = rows[1]
    for col in ["Sub-topic decision", "Corrected sub-topic", "Topic decision",
                "Corrected topic", "Question type decision", "Corrected question type", "Notes"]:
        assert row[COLUMNS.index(col)] == "", f"column '{col}' should be blank"


def test_missing_doc_id_leaves_meeting_fields_blank():
    """If doc_id doesn't match any ingested doc, meeting fields are blank."""
    theme = make_classified_theme(doc_id="doc-unknown")
    rows = build_classified_notes_rows([theme], [make_ingested_doc(doc_id="doc-001")])
    row = rows[1]
    assert row[COLUMNS.index("Meeting date")] == ""
    assert row[COLUMNS.index("Meeting body")] == ""
    assert row[COLUMNS.index("GDoc URL")] == ""


def test_date_raw_fallback_when_date_is_none():
    doc = make_ingested_doc(date=None, date_raw="February 10, 2026")
    rows = build_classified_notes_rows([make_classified_theme()], [doc])
    assert rows[1][COLUMNS.index("Meeting date")] == "February 10, 2026"


# ---------------------------------------------------------------------------
# Hard cases
# ---------------------------------------------------------------------------

def test_needs_review_row_has_all_agent_columns_populated():
    """A needs_review row still gets all agent columns filled, not just the flag."""
    theme = make_classified_theme(
        needs_review=True,
        merge_confidence=0.28,
        retrieved_context=[HOUSING_SIMILAR],
    )
    rows = build_classified_notes_rows([theme], [make_ingested_doc()])
    row = rows[1]
    assert row[COLUMNS.index("Sub-topic")] != ""
    assert row[COLUMNS.index("Topic")] != ""
    assert row[COLUMNS.index("Retrieved similar themes")] != ""
    assert row[COLUMNS.index("Needs review")] == "yes"


def test_cold_start_no_retrieved_context():
    """Cold start: empty retrieved_context produces empty string, no error."""
    theme = make_classified_theme(retrieved_context=[])
    rows = build_classified_notes_rows([theme], [make_ingested_doc()])
    assert rows[1][COLUMNS.index("Retrieved similar themes")] == ""


# ---------------------------------------------------------------------------
# Sheets I/O (mocked)
# ---------------------------------------------------------------------------

def _make_sheets_mock(existing_tab_titles: list[str] | None = None):
    # Use .return_value chains rather than calling () to avoid recording setup calls
    # in call_args_list, which would confuse index-based assertions.
    sheets = MagicMock()
    titles = existing_tab_titles or []
    sheets.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"title": t}} for t in titles]
    }
    sheets.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {
        "replies": [{"addSheet": {"properties": {"sheetId": 1}}}]
    }
    sheets.spreadsheets.return_value.values.return_value.update.return_value.execute.return_value = {}
    return sheets


def test_write_classified_notes_creates_tab():
    sheets = _make_sheets_mock()
    write_classified_notes([], [], sheets, "sheet-123", "2026-02-10")
    # First batchUpdate call is addSheet; second is formatting.
    batch_call = sheets.spreadsheets().batchUpdate.call_args_list[0]
    body = batch_call[1]["body"] if batch_call[1] else batch_call[0][1]
    assert body["requests"][0]["addSheet"]["properties"]["title"] == "classified-notes-2026-02-10-001"


def test_write_classified_notes_returns_tab_name():
    sheets = _make_sheets_mock()
    tab = write_classified_notes([], [], sheets, "sheet-123", "2026-02-10")
    assert tab == "classified-notes-2026-02-10-001"


def test_write_classified_notes_increments_on_same_day_rerun():
    sheets = _make_sheets_mock(existing_tab_titles=["classified-notes-2026-02-10-001"])
    tab = write_classified_notes([], [], sheets, "sheet-123", "2026-02-10")
    assert tab == "classified-notes-2026-02-10-002"


def test_write_classified_notes_writes_headers_for_empty_list():
    sheets = _make_sheets_mock()
    write_classified_notes([], [], sheets, "sheet-123", "2026-02-10")
    update_call = sheets.spreadsheets().values().update.call_args
    body = update_call[1]["body"] if update_call[1] else update_call[0][2]
    written_rows = body["values"]
    assert written_rows == [COLUMNS]


def test_write_classified_notes_writes_data_rows():
    sheets = _make_sheets_mock()
    theme = make_classified_theme()
    doc = make_ingested_doc()
    write_classified_notes([theme], [doc], sheets, "sheet-123", "2026-02-10")
    update_call = sheets.spreadsheets().values().update.call_args
    body = update_call[1]["body"] if update_call[1] else update_call[0][2]
    written_rows = body["values"]
    assert len(written_rows) == 2  # header + 1 data row


# ---------------------------------------------------------------------------
# format_tab
# ---------------------------------------------------------------------------

def test_format_tab_calls_batch_update():
    sheets = MagicMock()
    sheets.spreadsheets().batchUpdate().execute.return_value = {}
    format_tab(sheets, "sheet-id", 42, [80, 150], [])
    assert sheets.spreadsheets().batchUpdate.called


def test_format_tab_includes_freeze_request():
    sheets = MagicMock()
    sheets.spreadsheets().batchUpdate().execute.return_value = {}
    format_tab(sheets, "sheet-id", 42, [80], [])
    body = sheets.spreadsheets().batchUpdate.call_args.kwargs["body"]
    freeze_reqs = [r for r in body["requests"] if "updateSheetProperties" in r]
    assert len(freeze_reqs) == 1
    assert freeze_reqs[0]["updateSheetProperties"]["properties"]["gridProperties"]["frozenRowCount"] == 1


def test_format_tab_includes_bold_header_request():
    sheets = MagicMock()
    sheets.spreadsheets().batchUpdate().execute.return_value = {}
    format_tab(sheets, "sheet-id", 42, [80], [])
    body = sheets.spreadsheets().batchUpdate.call_args.kwargs["body"]
    bold_reqs = [
        r for r in body["requests"]
        if "repeatCell" in r and "textFormat" in r["repeatCell"]["cell"]["userEnteredFormat"]
    ]
    assert len(bold_reqs) == 1
    assert bold_reqs[0]["repeatCell"]["cell"]["userEnteredFormat"]["textFormat"]["bold"] is True


def test_format_tab_header_row_wraps():
    """Header row repeatCell request includes wrapStrategy: WRAP alongside bold."""
    sheets = MagicMock()
    sheets.spreadsheets().batchUpdate().execute.return_value = {}
    format_tab(sheets, "sheet-id", 42, [], [])
    body = sheets.spreadsheets().batchUpdate.call_args.kwargs["body"]
    header_req = next(
        r for r in body["requests"]
        if "repeatCell" in r and "startRowIndex" in r["repeatCell"]["range"]
    )
    fmt = header_req["repeatCell"]["cell"]["userEnteredFormat"]
    assert fmt["wrapStrategy"] == "WRAP"
    assert fmt["textFormat"]["bold"] is True


def test_format_tab_column_width_request_count():
    sheets = MagicMock()
    sheets.spreadsheets().batchUpdate().execute.return_value = {}
    format_tab(sheets, "sheet-id", 42, [80, 150, 300], [])
    body = sheets.spreadsheets().batchUpdate.call_args.kwargs["body"]
    width_reqs = [r for r in body["requests"] if "updateDimensionProperties" in r]
    assert len(width_reqs) == 3


def test_format_tab_column_widths_are_correct():
    sheets = MagicMock()
    sheets.spreadsheets().batchUpdate().execute.return_value = {}
    format_tab(sheets, "sheet-id", 42, [80, 400], [])
    body = sheets.spreadsheets().batchUpdate.call_args.kwargs["body"]
    width_reqs = [r for r in body["requests"] if "updateDimensionProperties" in r]
    assert width_reqs[0]["updateDimensionProperties"]["properties"]["pixelSize"] == 80
    assert width_reqs[1]["updateDimensionProperties"]["properties"]["pixelSize"] == 400


def _column_wrap_reqs(body: dict) -> list[dict]:
    """Extract wrap requests that target a column range (not the header row)."""
    return [
        r for r in body["requests"]
        if "repeatCell" in r
        and "startColumnIndex" in r["repeatCell"]["range"]
        and "wrapStrategy" in r["repeatCell"]["cell"]["userEnteredFormat"]
    ]


def test_format_tab_wrap_request_count():
    sheets = MagicMock()
    sheets.spreadsheets().batchUpdate().execute.return_value = {}
    format_tab(sheets, "sheet-id", 42, [], [2, 16])
    body = sheets.spreadsheets().batchUpdate.call_args.kwargs["body"]
    assert len(_column_wrap_reqs(body)) == 2


def test_format_tab_wrap_targets_correct_columns():
    sheets = MagicMock()
    sheets.spreadsheets().batchUpdate().execute.return_value = {}
    format_tab(sheets, "sheet-id", 42, [], [5])
    body = sheets.spreadsheets().batchUpdate.call_args.kwargs["body"]
    col_wraps = _column_wrap_reqs(body)
    assert col_wraps[0]["repeatCell"]["range"]["startColumnIndex"] == 5
    assert col_wraps[0]["repeatCell"]["range"]["endColumnIndex"] == 6


def test_format_tab_uses_correct_sheet_id():
    sheets = MagicMock()
    sheets.spreadsheets().batchUpdate().execute.return_value = {}
    format_tab(sheets, "sheet-id", 99, [80], [])
    body = sheets.spreadsheets().batchUpdate.call_args.kwargs["body"]
    freeze_req = next(r for r in body["requests"] if "updateSheetProperties" in r)
    assert freeze_req["updateSheetProperties"]["properties"]["sheetId"] == 99


def test_write_classified_notes_applies_formatting():
    """write_classified_notes calls format_tab after writing data (two batchUpdate calls)."""
    sheets = _make_sheets_mock()
    write_classified_notes([], [], sheets, "sheet-123", "2026-02-10")
    # Two batchUpdate calls: addSheet and format_tab.
    assert sheets.spreadsheets().batchUpdate.call_count == 2
    format_body = sheets.spreadsheets().batchUpdate.call_args_list[1].kwargs["body"]
    freeze_reqs = [r for r in format_body["requests"] if "updateSheetProperties" in r]
    assert len(freeze_reqs) == 1


def test_column_widths_length_matches_columns():
    assert len(_COLUMN_WIDTHS) == len(COLUMNS)


def test_wrap_columns_are_valid_indices():
    for idx in _WRAP_COLUMNS:
        assert 0 <= idx < len(COLUMNS)


# ---------------------------------------------------------------------------
# enrich_library_descriptions
# ---------------------------------------------------------------------------

def _make_library_record(sub_topic: str, description: str = "") -> ThemeRecord:
    return ThemeRecord(sub_topic=sub_topic, topics=[Topic.HOUSING], description=description)


def test_enrich_fills_empty_description():
    """Library record with no description gets it from a matching classified theme."""
    record = _make_library_record("lead pipe replacement funding")
    theme = make_classified_theme(
        sub_topic="lead pipe replacement funding",
        description="Funding gaps for replacing lead service lines.",
    )
    enrich_library_descriptions([record], [theme])
    assert record.description == "Funding gaps for replacing lead service lines."


def test_enrich_does_not_overwrite_existing_description():
    """Records with an existing description are not changed."""
    record = _make_library_record("lead pipe replacement funding", description="Original.")
    theme = make_classified_theme(
        sub_topic="lead pipe replacement funding",
        description="Different description.",
    )
    enrich_library_descriptions([record], [theme])
    assert record.description == "Original."


def test_enrich_ignores_unmatched_themes():
    """A classified theme whose sub_topic doesn't match any library record is skipped."""
    record = _make_library_record("school closure process")
    theme = make_classified_theme(sub_topic="lead pipe replacement funding")
    enrich_library_descriptions([record], [theme])
    assert record.description == ""


def test_enrich_skips_classified_themes_with_empty_description():
    """A classified theme with an empty description does not blank a library description."""
    record = _make_library_record("lead pipe replacement funding", description="Original.")
    theme = make_classified_theme(sub_topic="lead pipe replacement funding", description="")
    enrich_library_descriptions([record], [theme])
    assert record.description == "Original."


def test_enrich_no_op_on_empty_inputs():
    enrich_library_descriptions([], [])
    enrich_library_descriptions([_make_library_record("a")], [])
