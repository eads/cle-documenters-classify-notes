"""test_e2e.py — end-to-end fixture tests.

Smoke-tests the full pipeline against real Documenters notes captured as
text fixtures. The fixture files are checked into the repo so all CI tests
here run without any credentials.

CI tests (no LLM):
  - Every fixture passes the ingest gate.
  - Parsed question counts match the fixture content.
  - Known hard cases survive ingest intact (inline editor notes, long
    questions, formatting quirks).
  - The full graph completes on the "no questions" fixture — cold-start,
    no LLM calls required.

Integration tests (require OPENAI_API_KEY):
  - Each fixture runs through the full graph with a real LLM.
  - Results are smoke-tested for structural validity.
  - Stubs marked # TK: integration — not yet implemented.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from documenters_cle_langchain.graph import GraphState, build_graph
from documenters_cle_langchain.ingest import run_ingest

# ---------------------------------------------------------------------------
# Fixture loading helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


def _make_manifest_doc(doc_id: str, name: str, text: str) -> dict:
    return {
        "doc_id": doc_id,
        "name": name,
        "web_url": f"https://example.com/{doc_id}",
        "folder_path": "",
        "modified_time": "",
        "text": text,
    }


# ---------------------------------------------------------------------------
# Ingest — gate and question counts
# ---------------------------------------------------------------------------


def test_ingest_no_questions_passes_gate():
    """Urban Forestry: no Follow-Up Questions section → passes gate, 0 questions."""
    text = _load_fixture("fixture_no_questions.txt")
    doc = _make_manifest_doc("doc_urban_forestry", "Urban Forestry Budget Committee", text)
    ingested, skipped = run_ingest([doc])
    assert skipped == [], f"Unexpected gate failure: {skipped}"
    assert len(ingested) == 1
    assert ingested[0]["follow_up_questions"] == []


def test_ingest_single_question_passes_gate():
    """Health Committee: one indignant question → passes gate, 1 question."""
    text = _load_fixture("fixture_single_question.txt")
    doc = _make_manifest_doc("doc_health", "Health Committee", text)
    ingested, skipped = run_ingest([doc])
    assert skipped == []
    assert len(ingested) == 1
    assert len(ingested[0]["follow_up_questions"]) == 1


def test_ingest_inline_editor_note_passes_gate():
    """County Council: editor's note inline in first question → passes gate, 3 questions."""
    text = _load_fixture("fixture_inline_editor_note.txt")
    doc = _make_manifest_doc("doc_county_council", "Cuyahoga County Council", text)
    ingested, skipped = run_ingest([doc])
    assert skipped == []
    assert len(ingested) == 1
    assert len(ingested[0]["follow_up_questions"]) == 3


def test_ingest_inline_editor_note_survives_in_question():
    """Editor's note content is preserved as part of the question text."""
    text = _load_fixture("fixture_inline_editor_note.txt")
    doc = _make_manifest_doc("doc_county_council", "Cuyahoga County Council", text)
    ingested, _ = run_ingest([doc])
    first_q = ingested[0]["follow_up_questions"][0]
    # The editor's note is inline — it should survive question parsing
    assert "African Town" in first_q
    assert "Editor's note" in first_q


def test_ingest_land_bank_passes_gate():
    """Land Bank: 3 questions spanning governance/legal/housing → passes gate."""
    text = _load_fixture("fixture_land_bank.txt")
    doc = _make_manifest_doc("doc_land_bank", "Cuyahoga County Land Bank Board", text)
    ingested, skipped = run_ingest([doc])
    assert skipped == []
    assert len(ingested) == 1
    assert len(ingested[0]["follow_up_questions"]) == 3


def test_ingest_public_safety_passes_gate():
    """Public Safety Tech: 3 questions with accountability/continuity overlap → passes gate."""
    text = _load_fixture("fixture_public_safety.txt")
    doc = _make_manifest_doc("doc_public_safety", "Public Safety Technology Advisory Committee", text)
    ingested, skipped = run_ingest([doc])
    assert skipped == []
    assert len(ingested) == 1
    assert len(ingested[0]["follow_up_questions"]) == 3


def test_ingest_metadata_extracted_correctly():
    """Spot-check: agency, ISO date, and meeting name from the Health fixture."""
    text = _load_fixture("fixture_single_question.txt")
    doc = _make_manifest_doc("doc_health", "Health Committee", text)
    ingested, _ = run_ingest([doc])
    record = ingested[0]
    assert "Cleveland City Council" in record["agency"]
    assert record["date"] == "2026-01-12"
    assert "Health" in record["meeting_name"]


def test_ingest_batch_all_pass_gate():
    """All five fixtures pass the gate when ingested together."""
    manifest = [
        _make_manifest_doc("f1", "Urban Forestry", _load_fixture("fixture_no_questions.txt")),
        _make_manifest_doc("f2", "Health Committee", _load_fixture("fixture_single_question.txt")),
        _make_manifest_doc("f3", "County Council", _load_fixture("fixture_inline_editor_note.txt")),
        _make_manifest_doc("f4", "Land Bank", _load_fixture("fixture_land_bank.txt")),
        _make_manifest_doc("f5", "Public Safety", _load_fixture("fixture_public_safety.txt")),
    ]
    ingested, skipped = run_ingest(manifest)
    assert skipped == [], f"Unexpected gate failures: {[s['doc_id'] for s in skipped]}"
    assert len(ingested) == 5


def test_ingest_question_counts_batch():
    """Correct question counts across all five fixtures."""
    manifest = [
        _make_manifest_doc("f1", "Urban Forestry", _load_fixture("fixture_no_questions.txt")),
        _make_manifest_doc("f2", "Health Committee", _load_fixture("fixture_single_question.txt")),
        _make_manifest_doc("f3", "County Council", _load_fixture("fixture_inline_editor_note.txt")),
        _make_manifest_doc("f4", "Land Bank", _load_fixture("fixture_land_bank.txt")),
        _make_manifest_doc("f5", "Public Safety", _load_fixture("fixture_public_safety.txt")),
    ]
    ingested, _ = run_ingest(manifest)
    q_counts = {doc["doc_id"]: len(doc["follow_up_questions"]) for doc in ingested}
    assert q_counts["f1"] == 0, "Urban Forestry: no questions"
    assert q_counts["f2"] == 1, "Health Committee: one question"
    assert q_counts["f3"] == 3, "County Council: three questions"
    assert q_counts["f4"] == 3, "Land Bank: three questions"
    assert q_counts["f5"] == 3, "Public Safety: three questions"


# ---------------------------------------------------------------------------
# Full graph — cold-start, no LLM calls
# ---------------------------------------------------------------------------

_MINIMAL_STATE: GraphState = {
    "manifest_docs": [],
    "sheet_id": None,
    "run_date": "2026-03-25",
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


def test_graph_no_questions_no_llm_calls():
    """Full graph on the no-questions fixture: cold-start, no LLM instantiated.

    Urban Forestry has no Follow-Up Questions section → retrieval_context is
    empty → extract_candidates short-circuits before touching ChatOpenAI.
    """
    text = _load_fixture("fixture_no_questions.txt")
    state = {
        **_MINIMAL_STATE,
        "manifest_docs": [
            _make_manifest_doc("doc_urban_forestry", "Urban Forestry Budget Committee", text)
        ],
    }
    result = build_graph().invoke(state)

    assert len(result["ingested_docs"]) == 1
    assert result["ingested_docs"][0]["follow_up_questions"] == []
    assert result["retrieval_context"] == []
    assert result["candidates"] == []
    assert result["classified_themes"] == []
    assert result["run_summary"] == {"sheets_written": 0}


def test_graph_empty_manifest_no_llm():
    """Full graph with no docs: nothing to ingest or classify."""
    result = build_graph().invoke({**_MINIMAL_STATE, "manifest_docs": []})
    assert result["ingested_docs"] == []
    assert result["classified_themes"] == []
    assert result["run_summary"] == {"sheets_written": 0}


def test_graph_all_no_questions_batch_no_llm():
    """All five fixtures in one batch: Urban Forestry drives cold-start path.

    The other four fixtures have questions, so retrieval_context is non-empty
    and extract_candidates would fire — but all four are gated behind
    OPENAI_API_KEY. This test runs only the no-questions fixture.
    """
    text = _load_fixture("fixture_no_questions.txt")
    state = {
        **_MINIMAL_STATE,
        "manifest_docs": [
            _make_manifest_doc("doc_urban_forestry", "Urban Forestry Budget Committee", text)
        ],
    }
    result = build_graph().invoke(state)
    assert result["skipped_docs"] == []
    assert result["classified_themes"] == []


# ---------------------------------------------------------------------------
# Integration tests — require OPENAI_API_KEY
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_single_question_health_committee():
    """Full graph against Health Committee fixture with real LLM.

    Single question is skeptical/accountability-ambiguous. Expect exactly
    one ClassifiedTheme with a non-empty sub_topic.
    """
    # TK: integration
    pytest.skip("TK: integration — not yet implemented")


@pytest.mark.integration
def test_integration_inline_editor_note_county_council():
    """Full graph against County Council fixture with real LLM.

    Editor's note is inline in the first question. The LLM should handle
    it gracefully and return 3 classified themes. The Browns stadium question
    may span DEVELOPMENT + BUDGET topics — verify no crash, non-empty sub_topics.
    """
    # TK: integration
    pytest.skip("TK: integration — not yet implemented")


@pytest.mark.integration
def test_integration_land_bank():
    """Full graph against Land Bank fixture with real LLM.

    Third question spans governance/legal. Verify 3 classified themes, no crash.
    """
    # TK: integration
    pytest.skip("TK: integration — not yet implemented")


@pytest.mark.integration
def test_integration_public_safety():
    """Full graph against Public Safety fixture with real LLM.

    Questions 1-2 have accountability/continuity ambiguity. Verify 3 themes,
    non-empty question types.
    """
    # TK: integration
    pytest.skip("TK: integration — not yet implemented")


@pytest.mark.integration
def test_integration_all_fixtures_batch():
    """Full graph against all five fixtures in one batch with real LLM.

    Smoke test: all fixture docs should either produce ClassifiedThemes or
    land in skipped_docs — no unhandled exceptions.
    """
    # TK: integration
    pytest.skip("TK: integration — not yet implemented")
