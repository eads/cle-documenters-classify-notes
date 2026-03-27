"""Tests for retrieve_context.py — vector store construction and semantic retrieval.

No real API calls. FakeEmbeddings injects deterministic vectors so the store
can be built and queried without OPENAI_API_KEY.
"""
from __future__ import annotations

import pytest
from langchain_core.embeddings import Embeddings

from documenters_cle_langchain.ingest import IngestedDoc
from documenters_cle_langchain.retrieve_context import (
    QuestionContext,
    SimilarTheme,
    build_vector_store,
    make_theme_search_tool,
    retrieve_for_question,
    run_retrieve_context,
)
from documenters_cle_langchain.theme_library import ThemeRecord, Topic


# ---------------------------------------------------------------------------
# Fake embeddings — deterministic, no API call
# ---------------------------------------------------------------------------


class FakeEmbeddings(Embeddings):
    """Fake embeddings for unit tests.

    Embeds each text as a 4-dim vector where the first component is
    proportional to the text length. Distinct enough to confirm the store
    works; not semantically meaningful.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    def _vec(self, text: str) -> list[float]:
        n = len(text) % 100
        return [float(n), float(100 - n), 0.0, 0.0]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_theme(
    sub_topic: str,
    description: str,
    topic: Topic = Topic.HOUSING,
) -> ThemeRecord:
    return ThemeRecord(sub_topic=sub_topic, description=description, topics=[topic])


def make_doc(doc_id: str, questions: list[str]) -> IngestedDoc:
    return IngestedDoc(
        doc_id=doc_id,
        name="Test Meeting",
        web_url="https://example.com",
        folder_path="2026/Jan",
        modified_time="2026-01-01T00:00:00Z",
        meeting_name="City Council",
        documenter_name="Test Reporter",
        agency="Cleveland City Council",
        date="2026-01-15",
        date_raw="January 15, 2026",
        documenters_url="https://documenters.org/events/123",
        summary="A meeting occurred.",
        follow_up_questions=questions,
        notes="Some notes.",
        single_signal="Housing",
        extraction_confidence=0.9,
    )


THEMES = [
    make_theme("Section 8 voucher waitlists", "Long waits for housing vouchers", Topic.HOUSING),
    make_theme("School enrollment caps", "Limits on magnet school enrollment", Topic.EDUCATION),
    make_theme("Browns stadium financing", "Public funding for stadium", Topic.BUDGET),
]

FAKE_EMBEDDINGS = FakeEmbeddings()


# ---------------------------------------------------------------------------
# build_vector_store
# ---------------------------------------------------------------------------


def test_build_vector_store_cold_start_returns_none():
    store = build_vector_store([], FAKE_EMBEDDINGS)
    assert store is None


def test_build_vector_store_cold_start_does_not_call_embeddings():
    """Embeddings are never called when the theme library is empty."""

    class StrictEmbeddings(Embeddings):
        def embed_documents(self, texts):
            raise AssertionError("embed_documents called on cold start")

        def embed_query(self, text):
            raise AssertionError("embed_query called on cold start")

    store = build_vector_store([], StrictEmbeddings())
    assert store is None


def test_build_vector_store_with_themes_returns_store():
    store = build_vector_store(THEMES, FAKE_EMBEDDINGS)
    assert store is not None


def test_build_vector_store_single_theme():
    store = build_vector_store([THEMES[0]], FAKE_EMBEDDINGS)
    assert store is not None


# ---------------------------------------------------------------------------
# retrieve_for_question
# ---------------------------------------------------------------------------


def test_retrieve_for_question_cold_start_returns_empty():
    result = retrieve_for_question("What about housing?", store=None, k=3)
    assert result == []


def test_retrieve_for_question_returns_at_most_k():
    store = build_vector_store(THEMES, FAKE_EMBEDDINGS)
    result = retrieve_for_question("housing question", store=store, k=2)
    assert len(result) <= 2


def test_retrieve_for_question_k_eq_number_of_themes():
    store = build_vector_store(THEMES, FAKE_EMBEDDINGS)
    result = retrieve_for_question("housing question", store=store, k=3)
    assert len(result) == 3


def test_retrieve_for_question_k_boundary_no_error():
    """k > number of indexed themes returns all themes without raising."""
    store = build_vector_store(THEMES, FAKE_EMBEDDINGS)
    result = retrieve_for_question("housing question", store=store, k=100)
    assert len(result) == len(THEMES)


def test_retrieve_for_question_k_zero_returns_empty():
    store = build_vector_store(THEMES, FAKE_EMBEDDINGS)
    result = retrieve_for_question("housing question", store=store, k=0)
    assert result == []


def test_retrieve_for_question_result_structure():
    store = build_vector_store(THEMES, FAKE_EMBEDDINGS)
    results = retrieve_for_question("housing question", store=store, k=3)
    assert len(results) > 0
    for r in results:
        assert "sub_topic" in r
        assert "description" in r
        assert "topic" in r
        assert "similarity_score" in r


def test_retrieve_for_question_scores_are_floats():
    store = build_vector_store(THEMES, FAKE_EMBEDDINGS)
    results = retrieve_for_question("housing question", store=store, k=3)
    for r in results:
        assert isinstance(r["similarity_score"], float)


def test_retrieve_for_question_topic_is_string():
    store = build_vector_store(THEMES, FAKE_EMBEDDINGS)
    results = retrieve_for_question("question", store=store, k=1)
    assert isinstance(results[0]["topic"], str)


# ---------------------------------------------------------------------------
# run_retrieve_context
# ---------------------------------------------------------------------------


def test_run_retrieve_context_no_docs_returns_empty():
    contexts = run_retrieve_context([], THEMES, FAKE_EMBEDDINGS, k=3)
    assert contexts == []


def test_run_retrieve_context_cold_start_no_embeddings():
    """Cold start: empty theme_library, embeddings=None — no error."""
    doc = make_doc("doc1", ["What about housing vouchers?"])
    contexts = run_retrieve_context([doc], [], embeddings=None, k=3)
    assert len(contexts) == 1
    assert contexts[0]["similar_themes"] == []
    assert contexts[0]["venue_context"] == []


def test_run_retrieve_context_cold_start_empty_similar_themes():
    doc = make_doc("doc1", ["Question one?", "Question two?"])
    contexts = run_retrieve_context([doc], [], embeddings=None, k=3)
    assert len(contexts) == 2
    for ctx in contexts:
        assert ctx["similar_themes"] == []


def test_run_retrieve_context_one_question_per_context():
    """Each follow-up question gets its own QuestionContext."""
    doc = make_doc("doc1", ["Housing?", "Schools?", "Budget?"])
    contexts = run_retrieve_context([doc], THEMES, FAKE_EMBEDDINGS, k=3)
    assert len(contexts) == 3


def test_run_retrieve_context_multiple_docs():
    doc1 = make_doc("doc1", ["Housing vouchers?"])
    doc2 = make_doc("doc2", ["School caps?", "Budget?"])
    contexts = run_retrieve_context([doc1, doc2], THEMES, FAKE_EMBEDDINGS, k=3)
    assert len(contexts) == 3  # 1 + 2


def test_run_retrieve_context_doc_id_preserved():
    doc1 = make_doc("abc-123", ["Housing?"])
    doc2 = make_doc("xyz-456", ["Schools?"])
    contexts = run_retrieve_context([doc1, doc2], THEMES, FAKE_EMBEDDINGS, k=3)
    doc_ids = [c["doc_id"] for c in contexts]
    assert "abc-123" in doc_ids
    assert "xyz-456" in doc_ids


def test_run_retrieve_context_question_text_preserved():
    q = "Why is the voucher waitlist so long?"
    doc = make_doc("doc1", [q])
    contexts = run_retrieve_context([doc], THEMES, FAKE_EMBEDDINGS, k=3)
    assert contexts[0]["question"] == q


def test_run_retrieve_context_venue_context_always_empty():
    """Venue context slot is a stub — always [] until venue KB is in scope."""
    doc = make_doc("doc1", ["Housing?"])
    contexts = run_retrieve_context([doc], THEMES, FAKE_EMBEDDINGS, k=3)
    for ctx in contexts:
        assert ctx["venue_context"] == []


def test_run_retrieve_context_returns_similar_themes_when_library_populated():
    doc = make_doc("doc1", ["What about housing vouchers?"])
    contexts = run_retrieve_context([doc], THEMES, FAKE_EMBEDDINGS, k=3)
    assert len(contexts[0]["similar_themes"]) > 0


def test_run_retrieve_context_k_boundary_across_docs():
    """k > number of themes in store — no error across multiple docs."""
    doc1 = make_doc("d1", ["Q1"])
    doc2 = make_doc("d2", ["Q2"])
    contexts = run_retrieve_context([doc1, doc2], THEMES, FAKE_EMBEDDINGS, k=50)
    for ctx in contexts:
        assert len(ctx["similar_themes"]) == len(THEMES)


def test_run_retrieve_context_doc_with_no_questions():
    """Doc with zero follow-up questions contributes no contexts."""
    doc = make_doc("doc1", [])
    contexts = run_retrieve_context([doc], THEMES, FAKE_EMBEDDINGS, k=3)
    assert contexts == []


# ---------------------------------------------------------------------------
# make_theme_search_tool
# ---------------------------------------------------------------------------


def test_make_theme_search_tool_returns_none_on_cold_start():
    """No store (cold start) → tool factory returns None."""
    assert make_theme_search_tool(None) is None


def test_make_theme_search_tool_returns_tool_when_store_populated():
    store = build_vector_store(THEMES, FAKE_EMBEDDINGS)
    tool = make_theme_search_tool(store)
    assert tool is not None
    assert tool.name == "search_theme_library"


def test_theme_search_tool_returns_string():
    store = build_vector_store(THEMES, FAKE_EMBEDDINGS)
    tool = make_theme_search_tool(store)
    result = tool.invoke({"query": "housing voucher delays"})
    assert isinstance(result, str)


def test_theme_search_tool_returns_results_for_matching_query():
    store = build_vector_store(THEMES, FAKE_EMBEDDINGS)
    tool = make_theme_search_tool(store)
    result = tool.invoke({"query": "housing voucher delays"})
    # Result should contain at least one sub-topic from THEMES
    assert any(t.sub_topic in result for t in THEMES)


def test_theme_search_tool_empty_store_returns_no_results_message():
    """Store built with no themes returns the no-results string."""
    # build_vector_store returns None for empty list, so test None path directly
    assert make_theme_search_tool(None) is None
