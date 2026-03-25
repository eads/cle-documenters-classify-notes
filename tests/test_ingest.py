"""Tests for the ingest node: question parsing, gate routing, and graph integration.

parse_questions() is tested directly — it's the new logic this issue adds.
run_ingest() is tested for gate pass/fail routing.
The graph integration test confirms ingest populates GraphState correctly.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from documenters_cle_langchain.ingest import IngestedDoc, SkippedDoc, parse_questions, run_ingest
from documenters_cle_langchain.graph import GraphState, build_graph

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# parse_questions — list format variants
# ---------------------------------------------------------------------------

def test_numbered_list():
    blob = "1. How will the community respond?\n2. What happens to closed schools?"
    result = parse_questions(blob)
    assert result == [
        "How will the community respond?",
        "What happens to closed schools?",
    ]


def test_numbered_list_paren():
    blob = "1) First question\n2) Second question"
    result = parse_questions(blob)
    assert result == ["First question", "Second question"]


def test_bulleted_list_dash():
    blob = "- Why was the vote delayed?\n- Who approved the contract?"
    result = parse_questions(blob)
    assert result == ["Why was the vote delayed?", "Who approved the contract?"]


def test_bulleted_list_asterisk():
    blob = "* First question\n* Second question"
    result = parse_questions(blob)
    assert result == ["First question", "Second question"]


def test_bulleted_list_bullet_char():
    blob = "• What is the timeline?\n• Who is responsible?"
    result = parse_questions(blob)
    assert result == ["What is the timeline?", "Who is responsible?"]


def test_bare_lines():
    blob = "Why did this happen?\nWhat is the next step?\nWho was notified?"
    result = parse_questions(blob)
    assert result == [
        "Why did this happen?",
        "What is the next step?",
        "Who was notified?",
    ]


def test_single_line_paragraph():
    blob = "Why was the public comment period skipped for this contract?"
    result = parse_questions(blob)
    assert result == ["Why was the public comment period skipped for this contract?"]


def test_empty_blob_returns_empty():
    assert parse_questions("") == []


def test_whitespace_only_returns_empty():
    assert parse_questions("   \n  \n  ") == []


def test_blank_lines_between_questions_skipped():
    blob = "1. First question\n\n2. Second question\n\n3. Third question"
    result = parse_questions(blob)
    assert result == ["First question", "Second question", "Third question"]


# ---------------------------------------------------------------------------
# parse_questions — markdown stripping
# ---------------------------------------------------------------------------

def test_bold_question_stripped():
    blob = "**Who decides which neighborhoods are eligible?**"
    result = parse_questions(blob)
    assert result == ["Who decides which neighborhoods are eligible?"]


def test_italic_question_stripped():
    blob = "*Why was this decision made without public input?*"
    result = parse_questions(blob)
    assert result == ["Why was this decision made without public input?"]


def test_bold_in_list():
    blob = "1. Normal question\n**Bold question?**\n- Bullet question"
    result = parse_questions(blob)
    assert result == ["Normal question", "Bold question?", "Bullet question"]


# ---------------------------------------------------------------------------
# parse_questions — hard case fixture
# ---------------------------------------------------------------------------

def test_mixed_formatting_fixture():
    """Real-format fixture: numbered + bold + bulleted in same section."""
    blob = (FIXTURES / "hard_case_note.txt").read_text()
    # Extract just the follow-up section for this test
    lines = blob.splitlines()
    start = next(i for i, l in enumerate(lines) if "Follow-Up Questions" in l)
    end = next(i for i, l in enumerate(lines) if i > start and l.startswith("##"))
    section = "\n".join(lines[start + 1:end])

    result = parse_questions(section)
    assert len(result) == 4
    assert any("landlords notified" in q for q in result)
    assert any("weatherization pilot" in q and "funding" in q for q in result)
    assert any("neighborhoods" in q for q in result)
    assert any("appeals" in q for q in result)


# ---------------------------------------------------------------------------
# run_ingest — gate routing
# ---------------------------------------------------------------------------

FULL_DOC = """\
Ward 10 Community Meeting
Documenter name: Tommy Oddo
Agency: Cleveland City Council
Date: March 4, 2026
See more about this meeting at Documenters.org

Summary
Residents raised concerns about public safety.

### Follow-Up Questions
- How will the community respond?
- What happens to closed schools?

Notes
The meeting took place in the rectory of St. Mary's Church.

Single Signal
Community members are alarmed about recent violence in Collinwood.
"""

MISSING_AGENCY_DOC = """\
Some Meeting
Documenter name: Pat Jones
Date: March 1, 2026
See more about this meeting at Documenters.org

Summary
A brief summary.

Notes
Some notes here.
"""


def _manifest_doc(doc_id: str, text: str, name: str = "Test Doc") -> dict:
    return {"doc_id": doc_id, "name": name, "web_url": "", "folder_path": "", "modified_time": "", "text": text}


def test_passing_doc_appears_in_ingested():
    ingested, skipped = run_ingest([_manifest_doc("doc-1", FULL_DOC)])
    assert len(ingested) == 1
    assert len(skipped) == 0
    assert ingested[0]["doc_id"] == "doc-1"


def test_failing_doc_appears_in_skipped():
    ingested, skipped = run_ingest([_manifest_doc("doc-2", MISSING_AGENCY_DOC)])
    assert len(ingested) == 0
    assert len(skipped) == 1
    assert skipped[0]["doc_id"] == "doc-2"
    assert "agency" in skipped[0]["missing_fields"]


def test_mixed_batch_routes_correctly():
    docs = [
        _manifest_doc("good", FULL_DOC, "Good Doc"),
        _manifest_doc("bad", MISSING_AGENCY_DOC, "Bad Doc"),
    ]
    ingested, skipped = run_ingest(docs)
    assert len(ingested) == 1
    assert len(skipped) == 1


def test_empty_manifest_returns_empty():
    ingested, skipped = run_ingest([])
    assert ingested == []
    assert skipped == []


def test_questions_are_list_not_blob():
    ingested, _ = run_ingest([_manifest_doc("doc-1", FULL_DOC)])
    qs = ingested[0]["follow_up_questions"]
    assert isinstance(qs, list)
    assert all(isinstance(q, str) for q in qs)


def test_questions_parsed_correctly():
    ingested, _ = run_ingest([_manifest_doc("doc-1", FULL_DOC)])
    qs = ingested[0]["follow_up_questions"]
    assert len(qs) == 2
    assert "How will the community respond?" in qs
    assert "What happens to closed schools?" in qs


def test_no_follow_up_produces_empty_list():
    no_followup = """\
Budget Meeting
Documenter name: Alex Smith
Agency: City of Cleveland Urban Forestry Commission
Date: January 15, 2026
See more about this meeting at Documenters.org

Summary
The commission reviewed proposed budget cuts.

Notes
Meeting was held at City Hall.
"""
    ingested, _ = run_ingest([_manifest_doc("doc-1", no_followup)])
    assert ingested[0]["follow_up_questions"] == []


def test_extraction_fields_preserved():
    ingested, _ = run_ingest([_manifest_doc("doc-1", FULL_DOC)])
    doc = ingested[0]
    assert doc["meeting_name"] == "Ward 10 Community Meeting"
    assert doc["agency"] == "Cleveland City Council"
    assert doc["date"] == "2026-03-04"
    assert "public safety" in doc["summary"]
    assert "Collinwood" in doc["single_signal"]


# ---------------------------------------------------------------------------
# Graph integration — ingest node populates GraphState
# ---------------------------------------------------------------------------

MINIMAL_STATE: GraphState = {
    "manifest_docs": [],
    "sheet_id": None,
    "run_date": "2026-03-24",
    "theme_library": [],
    "prior_decisions": [],
    "ingested_docs": [],
    "skipped_docs": [],
    "retrieval_context": [],
    "candidates": [],
    "classified_themes": [],
    "needs_review": [],
    "run_summary": {},
}


def test_ingest_node_populates_state():
    state = {
        **MINIMAL_STATE,
        "manifest_docs": [_manifest_doc("doc-1", FULL_DOC, "Ward 10")],
    }
    graph = build_graph()
    result = graph.invoke(state)
    assert len(result["ingested_docs"]) == 1
    assert len(result["skipped_docs"]) == 0


def test_ingest_node_skips_bad_docs():
    state = {
        **MINIMAL_STATE,
        "manifest_docs": [_manifest_doc("doc-2", MISSING_AGENCY_DOC, "Bad Doc")],
    }
    graph = build_graph()
    result = graph.invoke(state)
    assert len(result["ingested_docs"]) == 0
    assert len(result["skipped_docs"]) == 1


def test_ingest_node_questions_in_state():
    state = {
        **MINIMAL_STATE,
        "manifest_docs": [_manifest_doc("doc-1", FULL_DOC)],
    }
    graph = build_graph()
    result = graph.invoke(state)
    qs = result["ingested_docs"][0]["follow_up_questions"]
    assert isinstance(qs, list)
    assert len(qs) == 2
