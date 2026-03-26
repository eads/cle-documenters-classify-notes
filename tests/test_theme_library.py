"""Tests for theme_library.py: schema, serialization, tab utilities, and Sheets I/O.

Sheets API calls are tested with mocks — no real credentials required.
Round-trip tests exercise the serialization layer directly.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from documenters_cle_langchain.theme_library import (
    COLUMNS,
    THEME_TAB_PREFIX,
    _COLUMN_WIDTHS,
    _WRAP_COLUMNS,
    QuestionType,
    ThemeRecord,
    Topic,
    find_latest_theme_tab,
    next_theme_tab_name,
    read_theme_library,
    write_theme_library,
)


# ---------------------------------------------------------------------------
# Taxonomy enums
# ---------------------------------------------------------------------------

def test_topic_enum_has_all_20():
    assert len(Topic) == 20


def test_topic_values_are_strings():
    for t in Topic:
        assert isinstance(t.value, str)


def test_known_topics_present():
    assert Topic.HOUSING.value == "HOUSING"
    assert Topic.CRIMINAL_JUSTICE.value == "CRIMINAL JUSTICE"
    assert Topic.PUBLIC_SAFETY.value == "PUBLIC SAFETY"
    assert Topic.CENSUS_2020.value == "CENSUS 2020"


def test_question_type_enum_has_all_5():
    assert len(QuestionType) == 5


def test_known_question_types_present():
    assert QuestionType.KNOWLEDGE_GAP.value == "knowledge_gap"
    assert QuestionType.SKEPTICISM.value == "skepticism"
    assert QuestionType.ACCOUNTABILITY.value == "accountability"


# ---------------------------------------------------------------------------
# ThemeRecord defaults and construction
# ---------------------------------------------------------------------------

def _housing_record(**kwargs) -> ThemeRecord:
    defaults = dict(
        sub_topic="Rental inspection enforcement",
        description="Questions about how rental inspection requirements are enforced",
        topics=[Topic.HOUSING],
    )
    return ThemeRecord(**{**defaults, **kwargs})


def test_theme_record_defaults():
    r = _housing_record()
    assert r.topics == [Topic.HOUSING]
    assert r.occurrence_count == 0
    assert r.knowledge_gap_count == 0
    assert r.representative_passages == []


def test_add_passage_appends():
    r = _housing_record()
    r.add_passage("How are landlords notified?")
    assert r.representative_passages == ["How are landlords notified?"]


def test_add_passage_caps_at_max():
    r = _housing_record()
    r.add_passage("Q1")
    r.add_passage("Q2")
    r.add_passage("Q3")
    r.add_passage("Q4 — should not be added")
    assert len(r.representative_passages) == 3
    assert "Q4 — should not be added" not in r.representative_passages


def test_add_passage_no_duplicates():
    r = _housing_record()
    r.add_passage("Same question")
    r.add_passage("Same question")
    assert r.representative_passages.count("Same question") == 1


# ---------------------------------------------------------------------------
# Serialization: to_row / from_row round-trip
# ---------------------------------------------------------------------------

def test_columns_count():
    assert len(COLUMNS) == 10


def test_to_row_length_matches_columns():
    r = _housing_record()
    assert len(r.to_row()) == len(COLUMNS)


def test_round_trip_basic():
    r = _housing_record(
        occurrence_count=5,
        knowledge_gap_count=3,
        accountability_count=2,
    )
    row = r.to_row()
    restored = ThemeRecord.from_row(row, COLUMNS)
    assert restored.sub_topic == r.sub_topic
    assert restored.description == r.description
    assert restored.topics == [Topic.HOUSING]
    assert restored.occurrence_count == 5
    assert restored.knowledge_gap_count == 3
    assert restored.accountability_count == 2


def test_round_trip_passages():
    r = _housing_record()
    r.add_passage("How are landlords notified?")
    r.add_passage("What are the penalties?")
    row = r.to_row()
    restored = ThemeRecord.from_row(row, COLUMNS)
    assert restored.representative_passages == [
        "How are landlords notified?",
        "What are the penalties?",
    ]


def test_round_trip_empty_passages():
    r = _housing_record()
    row = r.to_row()
    restored = ThemeRecord.from_row(row, COLUMNS)
    assert restored.representative_passages == []


def test_round_trip_multi_topic():
    """A sub-topic seen under multiple national topics survives round-trip."""
    r = _housing_record(topics=[Topic.HOUSING, Topic.EDUCATION])
    row = r.to_row()
    restored = ThemeRecord.from_row(row, COLUMNS)
    assert restored.topics == [Topic.HOUSING, Topic.EDUCATION]


def test_round_trip_topic_with_space():
    """Topics like 'CRIMINAL JUSTICE' must survive the round-trip."""
    r = _housing_record(topics=[Topic.CRIMINAL_JUSTICE])
    row = r.to_row()
    restored = ThemeRecord.from_row(row, COLUMNS)
    assert restored.topics == [Topic.CRIMINAL_JUSTICE]


def test_from_row_backward_compat_old_topic_column():
    """Old tabs with a single 'Topic' column (not 'Included in topics') are read correctly."""
    headers = ["Sub-topic", "Description", "Topic", "Occurrences"]
    row = ["Rent control", "About rent control", "HOUSING", "3"]
    r = ThemeRecord.from_row(row, headers)
    assert r.topics == [Topic.HOUSING]
    assert r.occurrence_count == 3


def test_from_row_tolerates_short_row():
    """Older tabs may have fewer columns — should not crash."""
    short_row = ["My sub-topic", "A description", "HOUSING"]
    r = ThemeRecord.from_row(short_row, COLUMNS)
    assert r.sub_topic == "My sub-topic"
    assert r.occurrence_count == 0


def test_from_row_tolerates_missing_column():
    """Column absent from headers entirely — uses default."""
    headers = ["Sub-topic", "Description", "Topic"]
    row = ["Rent control", "About rent control", "HOUSING"]
    r = ThemeRecord.from_row(row, headers)
    assert r.occurrence_count == 0
    assert r.representative_passages == []


# ---------------------------------------------------------------------------
# Tab utilities
# ---------------------------------------------------------------------------

def test_theme_tab_name_first_run():
    assert next_theme_tab_name("2026-03-24", []) == "theme-overview-2026-03-24-001"


def test_theme_tab_name_second_run():
    existing = ["theme-overview-2026-03-24-001"]
    assert next_theme_tab_name("2026-03-24", existing) == "theme-overview-2026-03-24-002"


def test_theme_tab_name_ignores_other_dates():
    existing = ["theme-overview-2026-03-23-001", "theme-overview-2026-03-23-002"]
    assert next_theme_tab_name("2026-03-24", existing) == "theme-overview-2026-03-24-001"


def test_find_latest_tab_returns_most_recent():
    tabs = [
        "theme-overview-2026-01-15-001",
        "Sheet1",
        "theme-overview-2026-03-01-001",
        "theme-overview-2025-12-10-001",
    ]
    assert find_latest_theme_tab(tabs) == "theme-overview-2026-03-01-001"


def test_find_latest_tab_returns_latest_within_same_day():
    tabs = [
        "theme-overview-2026-03-01-001",
        "theme-overview-2026-03-01-002",
        "theme-overview-2026-03-01-003",
    ]
    assert find_latest_theme_tab(tabs) == "theme-overview-2026-03-01-003"


def test_find_latest_tab_cold_start():
    """No theme library tabs → None."""
    tabs = ["Sheet1", "Classified notes 2026-01-15", "Results"]
    assert find_latest_theme_tab(tabs) is None


def test_find_latest_tab_empty_list():
    assert find_latest_theme_tab([]) is None


def test_find_latest_tab_ignores_non_prefix_matches():
    tabs = ["not-theme-overview-2026-01-01", "theme-overview-2026-02-01"]
    assert find_latest_theme_tab(tabs) == "theme-overview-2026-02-01"


# ---------------------------------------------------------------------------
# Sheets API: read_theme_library (mocked)
# ---------------------------------------------------------------------------

def _mock_sheets(tab_titles: list[str], rows: list[list]) -> MagicMock:
    """Build a minimal mock of the Sheets API client."""
    sheets = MagicMock()
    # spreadsheets().get() returns sheet metadata with tab titles
    sheets.spreadsheets().get().execute.return_value = {
        "sheets": [{"properties": {"title": t}} for t in tab_titles]
    }
    # spreadsheets().values().get() returns tab data
    sheets.spreadsheets().values().get().execute.return_value = {"values": rows}
    return sheets


def test_read_theme_library_cold_start():
    """No theme library tab → empty list, no crash."""
    sheets = _mock_sheets(["Sheet1", "Results"], [])
    result = read_theme_library(sheets, "sheet-id")
    assert result == []


def test_read_theme_library_empty_tab():
    """Tab exists but has no data rows → empty list."""
    sheets = _mock_sheets(["theme-overview-2026-01-01"], [COLUMNS])
    result = read_theme_library(sheets, "sheet-id")
    assert result == []


def test_read_theme_library_parses_records():
    r = _housing_record(occurrence_count=3)
    rows = [COLUMNS, r.to_row()]
    sheets = _mock_sheets(["theme-overview-2026-01-01"], rows)
    result = read_theme_library(sheets, "sheet-id")
    assert len(result) == 1
    assert result[0].sub_topic == r.sub_topic
    assert result[0].occurrence_count == 3


def test_read_theme_library_picks_latest_tab():
    """When multiple theme tabs exist, reads the most recent one."""
    r = _housing_record()
    rows = [COLUMNS, r.to_row()]
    sheets = _mock_sheets(
        ["theme-overview-2026-01-01", "theme-overview-2026-03-15"],
        rows,
    )
    read_theme_library(sheets, "sheet-id")
    # The values().get() call should reference the latest tab
    get_call_args = sheets.spreadsheets().values().get.call_args
    assert "theme-overview-2026-03-15" in str(get_call_args)


def test_read_theme_library_skips_malformed_rows(caplog):
    """A row with an invalid Topic value is skipped with a warning."""
    bad_row = ["Sub", "Desc", "NOT_A_VALID_TOPIC", "0", "0", "0", "0", "0", "0", ""]
    rows = [COLUMNS, bad_row]
    sheets = _mock_sheets(["theme-overview-2026-01-01"], rows)
    with caplog.at_level("WARNING"):
        result = read_theme_library(sheets, "sheet-id")
    assert result == []
    assert "skipping malformed row" in caplog.text


# ---------------------------------------------------------------------------
# Sheets API: write_theme_library (mocked)
# ---------------------------------------------------------------------------

def _write_mock(existing_tab_titles: list[str] | None = None) -> MagicMock:
    """Build a minimal Sheets mock for write_theme_library tests."""
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


def test_write_theme_library_creates_tab():
    sheets = _write_mock()
    records = [_housing_record()]
    tab = write_theme_library(records, sheets, "sheet-id", "2026-03-24")
    assert tab == "theme-overview-2026-03-24-001"


def test_write_theme_library_increments_on_same_day_rerun():
    sheets = _write_mock(existing_tab_titles=["theme-overview-2026-03-24-001"])
    tab = write_theme_library([], sheets, "sheet-id", "2026-03-24")
    assert tab == "theme-overview-2026-03-24-002"


def test_write_theme_library_writes_header_and_data():
    sheets = _write_mock()
    records = [_housing_record(occurrence_count=2)]
    write_theme_library(records, sheets, "sheet-id", "2026-03-24")
    update_call = sheets.spreadsheets().values().update.call_args
    written_rows = update_call.kwargs["body"]["values"]
    assert written_rows[0] == COLUMNS          # header row
    assert len(written_rows) == 2              # header + 1 record
    assert written_rows[1][0] == "Rental inspection enforcement"


def test_write_theme_library_empty_records():
    sheets = _write_mock()
    write_theme_library([], sheets, "sheet-id", "2026-03-24")
    update_call = sheets.spreadsheets().values().update.call_args
    written_rows = update_call.kwargs["body"]["values"]
    assert written_rows == [COLUMNS]           # header only


def test_write_theme_library_applies_formatting():
    """write_theme_library calls format_tab after writing data (two batchUpdate calls)."""
    sheets = _write_mock()
    write_theme_library([], sheets, "sheet-id", "2026-03-24")
    assert sheets.spreadsheets().batchUpdate.call_count == 2
    format_body = sheets.spreadsheets().batchUpdate.call_args_list[1].kwargs["body"]
    freeze_reqs = [r for r in format_body["requests"] if "updateSheetProperties" in r]
    assert len(freeze_reqs) == 1


def test_theme_overview_column_widths_length_matches_columns():
    assert len(_COLUMN_WIDTHS) == len(COLUMNS)


def test_theme_overview_wrap_columns_are_valid_indices():
    for idx in _WRAP_COLUMNS:
        assert 0 <= idx < len(COLUMNS)
