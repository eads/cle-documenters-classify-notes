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
        topics=[Topic.UTILITIES],
        occurrence_count=2,
    )
    return ThemeRecord(**{**defaults, **kwargs})


def make_decision(**kwargs) -> ReviewDecision:
    defaults: ReviewDecision = {  # type: ignore[assignment]
        "source_question": "When will the city replace the lead pipes?",
        "sub_topic": "lead pipe replacement funding",
        "description": "Funding gaps for replacing lead service lines.",
        "topic": "UTILITIES",
        "question_type": "knowledge_gap",
        "sub_topic_decision": DECISION_ACCEPT,
        "corrected_sub_topic": "",
        "topic_decision": "",
        "corrected_topic": "",
        "question_type_decision": "",
        "corrected_question_type": "",
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
        ["notes-2026-02-10"]
    ) == "notes-2026-02-10"


def test_find_latest_picks_most_recent():
    tabs = [
        "notes-2026-01-15",
        "notes-2026-03-01",
        "notes-2026-02-10",
        "theme-overview-2026-03-01",
    ]
    assert find_latest_classified_notes_tab(tabs) == "notes-2026-03-01"


def test_find_latest_empty_list():
    assert find_latest_classified_notes_tab([]) is None


def test_find_latest_versioned_picks_highest_version():
    tabs = [
        "notes-2026-03-01-001",
        "notes-2026-03-01-002",
        "notes-2026-03-01-003",
    ]
    assert find_latest_classified_notes_tab(tabs) == "notes-2026-03-01-003"


def test_find_latest_versioned_later_date_beats_higher_version():
    tabs = [
        "notes-2026-03-01-003",
        "notes-2026-03-02-001",
    ]
    assert find_latest_classified_notes_tab(tabs) == "notes-2026-03-02-001"


# ---------------------------------------------------------------------------
# apply_decisions — Accept
# ---------------------------------------------------------------------------

def test_accept_increments_existing_theme():
    library = [make_theme(occurrence_count=2)]
    decisions = [make_decision(sub_topic_decision=DECISION_ACCEPT)]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert theme.occurrence_count == 3


def test_accept_adds_passage_to_existing_theme():
    library = [make_theme()]
    decisions = [make_decision(sub_topic_decision=DECISION_ACCEPT, source_question="My lead pipe question")]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert "My lead pipe question" in theme.representative_passages


def test_accept_creates_new_theme_when_not_in_library():
    decisions = [make_decision(sub_topic_decision=DECISION_ACCEPT, sub_topic="new civic issue", topic="HOUSING")]
    result = apply_decisions([], decisions)
    assert len(result) == 1
    assert result[0].sub_topic == "new civic issue"
    assert Topic.HOUSING in result[0].topics
    assert result[0].occurrence_count == 1


def test_accept_increments_question_type_count():
    library = [make_theme(knowledge_gap_count=1)]
    decisions = [make_decision(sub_topic_decision=DECISION_ACCEPT, question_type="knowledge_gap")]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert theme.knowledge_gap_count == 2


def test_accept_uses_corrected_question_type_when_provided():
    library = [make_theme()]
    decisions = [make_decision(
        sub_topic_decision=DECISION_ACCEPT,
        question_type="knowledge_gap",
        question_type_decision=DECISION_RENAME,
        corrected_question_type="accountability",
    )]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert theme.accountability_count == 1
    assert theme.knowledge_gap_count == 0


# ---------------------------------------------------------------------------
# apply_decisions — Reject
# ---------------------------------------------------------------------------

def test_reject_does_not_add_theme():
    decisions = [make_decision(sub_topic_decision=DECISION_REJECT, sub_topic="should not appear")]
    result = apply_decisions([], decisions)
    assert result == []


def test_reject_does_not_increment_existing_theme():
    library = [make_theme(occurrence_count=2)]
    decisions = [make_decision(sub_topic_decision=DECISION_REJECT)]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert theme.occurrence_count == 2


# ---------------------------------------------------------------------------
# apply_decisions — Rename
# ---------------------------------------------------------------------------

def test_rename_to_existing_theme_increments_count():
    existing = make_theme(sub_topic="Section 8 voucher waitlists", topics=[Topic.HOUSING], occurrence_count=3)
    decisions = [make_decision(
        sub_topic_decision=DECISION_RENAME,
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
        topics=[Topic.HOUSING],
    )
    existing.add_passage("When will the city replace the lead pipes?")
    decisions = [make_decision(
        sub_topic_decision=DECISION_RENAME,
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
        sub_topic_decision=DECISION_RENAME,
        sub_topic="bad label",
        corrected_sub_topic="better label",
        topic="EDUCATION",
    )]
    result = apply_decisions([], decisions)
    assert len(result) == 1
    assert result[0].sub_topic == "better label"
    assert Topic.EDUCATION in result[0].topics
    assert result[0].occurrence_count == 1


def test_rename_with_blank_corrected_label_is_skipped():
    decisions = [make_decision(
        sub_topic_decision=DECISION_RENAME,
        sub_topic="some label",
        corrected_sub_topic="",
    )]
    result = apply_decisions([], decisions)
    assert result == []


def test_rename_original_label_not_added_to_library():
    """The original (wrong) sub_topic should not appear in the library."""
    decisions = [make_decision(
        sub_topic_decision=DECISION_RENAME,
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
    decisions = [make_decision(sub_topic_decision="")]
    result = apply_decisions([], decisions)
    assert result == []


def test_unknown_decision_is_skipped():
    decisions = [make_decision(sub_topic_decision="Undecided")]
    result = apply_decisions([], decisions)
    assert result == []


# ---------------------------------------------------------------------------
# apply_decisions — Case-insensitive decision matching (Issue #46)
# ---------------------------------------------------------------------------

def test_uppercase_accept_is_treated_as_accept():
    decisions = [make_decision(sub_topic_decision="ACCEPT", sub_topic="some theme", topic="HOUSING")]
    result = apply_decisions([], decisions)
    assert len(result) == 1


def test_uppercase_rename_is_treated_as_rename():
    decisions = [make_decision(
        sub_topic_decision="RENAME",
        sub_topic="bad label",
        corrected_sub_topic="good label",
        topic="HOUSING",
    )]
    result = apply_decisions([], decisions)
    assert len(result) == 1
    assert result[0].sub_topic == "good label"


def test_uppercase_reject_is_treated_as_reject():
    decisions = [make_decision(sub_topic_decision="REJECT", sub_topic="should not appear")]
    result = apply_decisions([], decisions)
    assert result == []


def test_lowercase_accept_is_treated_as_accept():
    decisions = [make_decision(sub_topic_decision="accept", sub_topic="some theme", topic="HOUSING")]
    result = apply_decisions([], decisions)
    assert len(result) == 1


def test_lowercase_rename_is_treated_as_rename():
    decisions = [make_decision(
        sub_topic_decision="rename",
        sub_topic="bad label",
        corrected_sub_topic="good label",
        topic="HOUSING",
    )]
    result = apply_decisions([], decisions)
    assert len(result) == 1
    assert result[0].sub_topic == "good label"


# ---------------------------------------------------------------------------
# apply_decisions — Base library preservation
# ---------------------------------------------------------------------------

def test_base_themes_not_referenced_by_decisions_are_preserved():
    library = [
        make_theme(sub_topic="lead pipe replacement funding"),
        make_theme(sub_topic="school closure process", topics=[Topic.EDUCATION]),
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
        sub_topic_decision=DECISION_ACCEPT,
        sub_topic="brand new theme",
        topic="NOT_A_REAL_TOPIC",
    )]
    result = apply_decisions([], decisions)
    assert len(result) == 1
    assert Topic.DEVELOPMENT in result[0].topics


def test_accept_adds_new_topic_to_existing_themes_list():
    """Accepting a question under a different topic adds that topic to the list."""
    library = [make_theme(topics=[Topic.UTILITIES])]
    decisions = [make_decision(sub_topic_decision=DECISION_ACCEPT, topic="HOUSING")]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert Topic.UTILITIES in theme.topics
    assert Topic.HOUSING in theme.topics


def test_accept_does_not_duplicate_topic():
    """Accepting the same topic twice does not create duplicates."""
    library = [make_theme(topics=[Topic.UTILITIES])]
    decisions = [
        make_decision(sub_topic_decision=DECISION_ACCEPT, topic="UTILITIES"),
        make_decision(sub_topic_decision=DECISION_ACCEPT, topic="UTILITIES", source_question="Q2"),
    ]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert theme.topics.count(Topic.UTILITIES) == 1


def test_accept_seeds_description_when_empty():
    """Description is populated from first decision row when record has none."""
    library = [make_theme(description="")]
    decisions = [make_decision(
        sub_topic_decision=DECISION_ACCEPT,
        description="Funding gaps for replacing lead service lines.",
    )]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert theme.description == "Funding gaps for replacing lead service lines."


def test_accept_does_not_overwrite_existing_description():
    """Existing description is preserved even when the decision row carries one."""
    library = [make_theme(description="Original description.")]
    decisions = [make_decision(
        sub_topic_decision=DECISION_ACCEPT,
        description="Different description.",
    )]
    result = apply_decisions(library, decisions)
    theme = next(r for r in result if r.sub_topic == "lead pipe replacement funding")
    assert theme.description == "Original description."


def test_rename_seeds_description_on_new_theme():
    """Rename to a new label seeds the description from the decision row."""
    decisions = [make_decision(
        sub_topic_decision=DECISION_RENAME,
        sub_topic="bad label",
        corrected_sub_topic="better label",
        topic="EDUCATION",
        description="A description for the renamed theme.",
    )]
    result = apply_decisions([], decisions)
    assert result[0].description == "A description for the renamed theme."


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
        ["notes-2026-02-10"],
        [NOTES_COLUMNS],  # header only, no data rows
    )
    result = read_classified_notes_decisions(sheets, "sheet-id")
    assert result == []


def test_read_decisions_parses_rows():
    data_row = [""] * len(NOTES_COLUMNS)
    data_row[NOTES_COLUMNS.index("Source question")] = "Lead pipe question"
    data_row[NOTES_COLUMNS.index("Sub-topic")] = "lead pipe replacement funding"
    data_row[NOTES_COLUMNS.index("Sub-topic description")] = "Funding gaps."
    data_row[NOTES_COLUMNS.index("Topic")] = "UTILITIES"
    data_row[NOTES_COLUMNS.index("Question type")] = "knowledge_gap"
    data_row[NOTES_COLUMNS.index("Sub-topic decision")] = "Accept"
    data_row[NOTES_COLUMNS.index("Corrected sub-topic")] = ""
    data_row[NOTES_COLUMNS.index("Corrected question type")] = ""

    sheets = _make_sheets_mock(
        ["notes-2026-02-10"],
        [NOTES_COLUMNS, data_row],
    )
    result = read_classified_notes_decisions(sheets, "sheet-id")
    assert len(result) == 1
    assert result[0]["source_question"] == "Lead pipe question"
    assert result[0]["sub_topic"] == "lead pipe replacement funding"
    assert result[0]["description"] == "Funding gaps."
    assert result[0]["sub_topic_decision"] == "Accept"


def test_read_decisions_uses_most_recent_tab():
    data_row = [""] * len(NOTES_COLUMNS)
    data_row[NOTES_COLUMNS.index("Sub-topic decision")] = "Reject"

    sheets = _make_sheets_mock(
        ["notes-2026-01-01", "notes-2026-03-25"],
        [NOTES_COLUMNS, data_row],
    )
    result = read_classified_notes_decisions(sheets, "sheet-id")
    # Should read the most recent tab; verify the values() call used the right tab
    get_call = sheets.spreadsheets().values().get.call_args
    assert "notes-2026-03-25" in str(get_call)


def test_read_decisions_tolerates_short_rows():
    """Rows shorter than the header should not raise."""
    short_row = ["short"]  # far fewer columns than the header
    sheets = _make_sheets_mock(
        ["notes-2026-02-10"],
        [NOTES_COLUMNS, short_row],
    )
    result = read_classified_notes_decisions(sheets, "sheet-id")
    assert len(result) == 1
    assert result[0]["sub_topic_decision"] == ""
