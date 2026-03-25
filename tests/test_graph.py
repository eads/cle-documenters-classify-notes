"""Tests for the LangGraph scaffold: state schema, graph topology, and invocation.

These tests verify structural correctness — that the graph can be built and
invoked, state keys are present, and the topology is wired correctly. No LLM
calls are made here (all nodes are stubs).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from documenters_cle_langchain.graph import GraphConfig, GraphState, build_graph


# ---------------------------------------------------------------------------
# Fixtures
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


# ---------------------------------------------------------------------------
# GraphConfig
# ---------------------------------------------------------------------------

def test_default_config_has_expected_models():
    config = GraphConfig()
    assert config.extract_model == "gpt-5.4"
    assert config.classify_model == "gpt-5.4"
    assert config.question_type_model == "gpt-5.4"
    assert config.embedding_model == "text-embedding-3-small"


def test_default_config_retrieval_k():
    config = GraphConfig()
    assert config.retrieval_k == 3


def test_default_config_review_threshold():
    config = GraphConfig()
    assert config.review_confidence_threshold == 0.4


def test_config_is_overridable():
    config = GraphConfig(extract_model="gpt-5-mini", retrieval_k=5)
    assert config.extract_model == "gpt-5-mini"
    assert config.retrieval_k == 5
    # Other fields unchanged
    assert config.classify_model == "gpt-5.4"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def test_build_graph_returns_compiled_graph():
    graph = build_graph()
    assert graph is not None


def test_build_graph_accepts_config():
    config = GraphConfig(extract_model="gpt-5-mini")
    graph = build_graph(config=config)
    assert graph is not None


def test_build_graph_default_config():
    # build_graph() with no args should use GraphConfig() defaults
    graph = build_graph()
    assert graph is not None


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

def test_graphstate_has_all_required_keys():
    """All expected keys are present in the state schema."""
    expected_keys = {
        "manifest_docs",
        "sheet_id",
        "run_date",
        "theme_library",
        "prior_decisions",
        "ingested_docs",
        "skipped_docs",
        "retrieval_context",
        "candidates",
        "classified_themes",
        "needs_review",
        "run_summary",
    }
    # GraphState is a TypedDict — __annotations__ gives us the declared keys
    assert expected_keys == set(GraphState.__annotations__.keys())


# ---------------------------------------------------------------------------
# Graph invocation (stub pass-through)
# ---------------------------------------------------------------------------

def test_graph_invokes_without_error():
    graph = build_graph()
    result = graph.invoke(MINIMAL_STATE)
    assert result is not None


def test_graph_preserves_input_state_keys():
    """All input keys survive the graph invocation (stubs return {}, no deletions)."""
    graph = build_graph()
    result = graph.invoke(MINIMAL_STATE)
    for key in MINIMAL_STATE:
        assert key in result, f"Key '{key}' missing from graph output"


def test_graph_passes_through_manifest_docs():
    docs = [{"doc_id": "abc", "name": "Test Meeting", "text": "..."}]
    state = {**MINIMAL_STATE, "manifest_docs": docs}
    graph = build_graph()
    result = graph.invoke(state)
    assert result["manifest_docs"] == docs


def test_graph_passes_through_run_date():
    state = {**MINIMAL_STATE, "run_date": "2026-01-15"}
    graph = build_graph()
    result = graph.invoke(state)
    assert result["run_date"] == "2026-01-15"


def test_graph_passes_through_sheet_id():
    # load_library and write_back are real now — patch all Sheets I/O so this
    # pass-through test doesn't require credentials.
    state = {**MINIMAL_STATE, "sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"}
    graph = build_graph()
    with (
        patch("documenters_cle_langchain.theme_library.build_sheets_client", return_value=MagicMock()),
        patch("documenters_cle_langchain.theme_library.read_theme_library", return_value=[]),
        patch("documenters_cle_langchain.feedback.read_classified_notes_decisions", return_value=[]),
        patch("documenters_cle_langchain.write_back.write_classified_notes", return_value="classified-notes-2026-03-24"),
        patch("documenters_cle_langchain.theme_library.write_theme_library", return_value="theme-overview-2026-03-24"),
    ):
        result = graph.invoke(state)
    assert result["sheet_id"] == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
