"""Tests for feedback.py — decision routing, library derivation, and Sheets I/O.

apply_decisions is the pure core and is tested exhaustively without credentials.
Sheets reads are tested with mocks.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from documenters_cle_langchain.feedback import (
    DECISION_ACCEPT,
    DECISION_REJECT,
    DECISION_RENAME,
    ReviewDecision,
    apply_decisions,
    find_latest_classified_notes_tab,
    read_classified_notes_decisions,
)
from documenters_cle_langchain.theme_library import ThemeRecord, Topic
from documenters_cle_langchain.write_back import COLUMNS as NOTES_COLUMNS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_theme(**kwargs) -> ThemeRecord:
    defaults = dict(
        sub_topic="lead pipe replacement funding",
        description="Funding gaps for replacing lead service lines.",
        topic=Topic.UTILITIES,
        occurrence_count=2,
    )
    return ThemeRecord(**{**defaults, **kwargs})


def make_decision(**kwargs) -> ReviewDecision:
    defaults: ReviewDecision = {  # type: ignore[assignment]
        "source_question": "When will the city replace the lead pipes?",
        "sub_topic": "lead pipe replacement funding",
        "topic": "UTILITIES",
        "question_type": "knowledge_gap",
        "decision": DECISION_ACCEPT,
        "corrected_sub_topic": "",
        "question_type_override": "",
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# find_latest_classified_notes_tab
# ---------------------------------------------------------------------------

def test_find_latest_no_classified_tabs():
    assert find_latest_classified_notes_tab(["theme-overview-2026-02-01"]) is None


def test_find_latest_single_tab():
    assert find_latest_classified_notes_tab(
        ["classified-notes-2026-02-10"]
    ) == "classified-notes-2026-02-10"


def test_find_latest_picks_most_recent():
    tabs = [
        "classified-notes-2026-01-15",
        "classified-notes-2026-03-01",
        "classified-notes-2026-02-10",
        "theme-overview-2026-03-01",
    ]
    assert find_latest_classified_notes_tab(tabs) == "classified-notes-2026-03-01"


def test_find_latest_empty_list():
    assert find_latest_classified_notes_tab([]) is None


# ---------------------------------------------------------------------------
# apply_decisions — Accept
# ---------------------------------------------------------------------------

def test_accept_increments_existing_theme():
    library = [make_theme(occurrence_count=2)]
    decisions = [make_decision(decision=DECISION_ACCEPT)]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert theme.occurrence_count == 3


def test_accept_adds_passage_to_existing_theme():
    library = [make_theme()]
    decisions = [make_decision(decision=DECISION_ACCEPT, source_question="My lead pipe question")]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert "My lead pipe question" in theme.representative_passages


def test_accept_creates_new_theme_when_not_in_library():
    decisions = [make_decision(decision=DECISION_ACCEPT, sub_topic="new civic issue", topic="HOUSING")]
    result = apply_decisions([], decisions)
    assert len(result) == 1
    assert result[0].sub_topic == "new civic issue"
    assert result[0].topic == Topic.HOUSING
    assert result[0].occurrence_count == 1


def test_accept_increments_question_type_count():
    library = [make_theme(knowledge_gap_count=1)]
    decisions = [make_decision(decision=DECISION_ACCEPT, question_type="knowledge_gap")]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert theme.knowledge_gap_count == 2


def test_accept_uses_question_type_override_when_provided():
    library = [make_theme()]
    decisions = [make_decision(
        decision=DECISION_ACCEPT,
        question_type="knowledge_gap",
        question_type_override="accountability",
    )]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert theme.accountability_count == 1
    assert theme.knowledge_gap_count == 0


# ---------------------------------------------------------------------------
# apply_decisions — Reject
# ---------------------------------------------------------------------------

def test_reject_does_not_add_theme():
    decisions = [make_decision(decision=DECISION_REJECT, sub_topic="should not appear")]
    result = apply_decisions([], decisions)
    assert result == []


def test_reject_does_not_increment_existing_theme():
    library = [make_theme(occurrence_count=2)]
    decisions = [make_decision(decision=DECISION_REJECT)]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert theme.occurrence_count == 2


# ---------------------------------------------------------------------------
# apply_decisions — Rename
# ---------------------------------------------------------------------------

def test_rename_to_existing_theme_increments_count():
    existing = make_theme(sub_topic="Section 8 voucher waitlists", topic=Topic.HOUSING, occurrence_count=3)
    decisions = [make_decision(
        decision=DECISION_RENAME,
        sub_topic="housing voucher delays",
        corrected_sub_topic="Section 8 voucher waitlists",
        topic="HOUSING",
    )]
    result = apply_decisions([existing], decisions)
    theme = next(r for r in result if r.sub_topic == "Section 8 voucher waitlists")
    assert theme.occurrence_count == 4


def test_rename_to_existing_adds_passage_without_duplication():
    existing = make_theme(
        sub_topic="Section 8 voucher waitlists",
        topic=Topic.HOUSING,
    )
    existing.add_passage("When will the city replace the lead pipes?")
    decisions = [make_decision(
        decision=DECISION_RENAME,
        source_question="When will the city replace the lead pipes?",
        corrected_sub_topic="Section 8 voucher waitlists",
        topic="HOUSING",
    )]
    result = apply_decisions([existing], decisions)
    theme = next(r for r in result if r.sub_topic == "Section 8 voucher waitlists")
    # No duplicate passage
    assert theme.representative_passages.count("When will the city replace the lead pipes?") == 1


def test_rename_to_new_label_creates_theme():
    decisions = [make_decision(
        decision=DECISION_RENAME,
        sub_topic="bad label",
        corrected_sub_topic="better label",
        topic="EDUCATION",
    )]
    result = apply_decisions([], decisions)
    assert len(result) == 1
    assert result[0].sub_topic == "better label"
    assert result[0].topic == Topic.EDUCATION
    assert result[0].occurrence_count == 1


def test_rename_with_blank_corrected_label_is_skipped():
    decisions = [make_decision(
        decision=DECISION_RENAME,
        sub_topic="some label",
        corrected_sub_topic="",
    )]
    result = apply_decisions([], decisions)
    assert result == []


def test_rename_original_label_not_added_to_library():
    """The original (wrong) sub_topic should not appear in the library."""
    decisions = [make_decision(
        decision=DECISION_RENAME,
        sub_topic="wrong label",
        corrected_sub_topic="correct label",
        topic="HOUSING",
    )]
    result = apply_decisions([], decisions)
    labels = [r.sub_topic for r in result]
    assert "wrong label" not in labels
    assert "correct label" in labels


# ---------------------------------------------------------------------------
# apply_decisions — Blank / unknown
# ---------------------------------------------------------------------------

def test_blank_decision_is_skipped():
    decisions = [make_decision(decision="")]
    result = apply_decisions([], decisions)
    assert result == []


def test_unknown_decision_is_skipped():
    decisions = [make_decision(decision="Undecided")]
    result = apply_decisions([], decisions)
    assert result == []


# ---------------------------------------------------------------------------
# apply_decisions — Base library preservation
# ---------------------------------------------------------------------------

def test_base_themes_not_referenced_by_decisions_are_preserved():
    library = [
        make_theme(sub_topic="lead pipe replacement funding"),
        make_theme(sub_topic="school closure process", topic=Topic.EDUCATION),
    ]
    decisions = [make_decision(sub_topic="lead pipe replacement funding")]
    result = apply_decisions(library, decisions)
    labels = {r.sub_topic for r in result}
    assert "school closure process" in labels


def test_empty_decisions_returns_base_library_unchanged():
    library = [make_theme(occurrence_count=5)]
    result = apply_decisions(library, [])
    assert len(result) == 1
    assert result[0].occurrence_count == 5


# ---------------------------------------------------------------------------
# Cold start
# ---------------------------------------------------------------------------

def test_cold_start_empty_base_and_empty_decisions():
    result = apply_decisions([], [])
    assert result == []


def test_cold_start_empty_base_with_accept_creates_themes():
    decisions = [
        make_decision(sub_topic="theme one", topic="HOUSING"),
        make_decision(sub_topic="theme two", topic="EDUCATION"),
    ]
    result = apply_decisions([], decisions)
    labels = {r.sub_topic for r in result}
    assert "theme one" in labels
    assert "theme two" in labels


# ---------------------------------------------------------------------------
# Hard cases
# ---------------------------------------------------------------------------

def test_multiple_accepts_for_same_theme_accumulate():
    decisions = [
        make_decision(sub_topic="recurring theme", topic="HOUSING", source_question="Q1"),
        make_decision(sub_topic="recurring theme", topic="HOUSING", source_question="Q2"),
    ]
    result = apply_decisions([], decisions)
    assert len(result) == 1
    assert result[0].occurrence_count == 2


def test_unknown_topic_string_defaults_gracefully():
    """An unrecognised topic value falls back to DEVELOPMENT without raising."""
    decisions = [make_decision(
        decision=DECISION_ACCEPT,
        sub_topic="brand new theme",
        topic="NOT_A_REAL_TOPIC",
    )]
    result = apply_decisions([], decisions)
    assert len(result) == 1
    assert result[0].topic == Topic.DEVELOPMENT


def test_all_question_type_counts_increment_correctly():
    library = [make_theme()]
    qt_map = {
        "knowledge_gap": "knowledge_gap_count",
        "process_confusion": "process_confusion_count",
        "skepticism": "skepticism_count",
        "accountability": "accountability_count",
        "continuity": "continuity_count",
    }
    for qt, field in qt_map.items():
        dec = make_decision(question_type=qt)
        result = apply_decisions([make_theme()], [dec])
        theme = result[0]
        assert getattr(theme, field) == 1, f"{field} should be 1 after one {qt} decision"


# ---------------------------------------------------------------------------
# read_classified_notes_decisions (mocked Sheets)
# ---------------------------------------------------------------------------

def _make_sheets_mock(tab_titles: list[str], rows: list[list]) -> MagicMock:
    sheets = MagicMock()
    sheets.spreadsheets().get().execute.return_value = {
        "sheets": [{"properties": {"title": t}} for t in tab_titles]
    }
    sheets.spreadsheets().values().get().execute.return_value = {"values": rows}
    return sheets


def test_read_decisions_cold_start_no_tabs():
    sheets = _make_sheets_mock([], [])
    result = read_classified_notes_decisions(sheets, "sheet-id")
    assert result == []


def test_read_decisions_empty_tab():
    sheets = _make_sheets_mock(
        ["classified-notes-2026-02-10"],
        [NOTES_COLUMNS],  # header only, no data rows
    )
    result = read_classified_notes_decisions(sheets, "sheet-id")
    assert result == []


def test_read_decisions_parses_rows():
    data_row = [""] * len(NOTES_COLUMNS)
    data_row[NOTES_COLUMNS.index("Source question")] = "Lead pipe question"
    data_row[NOTES_COLUMNS.index("Sub-topic")] = "lead pipe replacement funding"
    data_row[NOTES_COLUMNS.index("Topic")] = "UTILITIES"
    data_row[NOTES_COLUMNS.index("Question type")] = "knowledge_gap"
    data_row[NOTES_COLUMNS.index("Decision")] = "Accept"
    data_row[NOTES_COLUMNS.index("Corrected sub-topic")] = ""
    data_row[NOTES_COLUMNS.index("Question type override")] = ""

    sheets = _make_sheets_mock(
        ["classified-notes-2026-02-10"],
        [NOTES_COLUMNS, data_row],
    )
    result = read_classified_notes_decisions(sheets, "sheet-id")
    assert len(result) == 1
    assert result[0]["source_question"] == "Lead pipe question"
    assert result[0]["sub_topic"] == "lead pipe replacement funding"
    assert result[0]["decision"] == "Accept"


def test_read_decisions_uses_most_recent_tab():
    data_row = [""] * len(NOTES_COLUMNS)
    data_row[NOTES_COLUMNS.index("Decision")] = "Reject"

    sheets = _make_sheets_mock(
        ["classified-notes-2026-01-01", "classified-notes-2026-03-25"],
        [NOTES_COLUMNS, data_row],
    )
    result = read_classified_notes_decisions(sheets, "sheet-id")
    # Should read the most recent tab; verify the values() call used the right tab
    get_call = sheets.spreadsheets().values().get.call_args
    assert "classified-notes-2026-03-25" in str(get_call)


def test_read_decisions_tolerates_short_rows():
    """Rows shorter than the header should not raise."""
    short_row = ["short"]  # far fewer columns than the header
    sheets = _make_sheets_mock(
        ["classified-notes-2026-02-10"],
        [NOTES_COLUMNS, short_row],
    )
    result = read_classified_notes_decisions(sheets, "sheet-id")
    assert len(result) == 1
    assert result[0]["decision"] == ""
