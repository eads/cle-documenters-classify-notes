"""graph.py — LangGraph agent for meeting note theme extraction and classification.

Graph topology:
    [ingest] → [retrieve_context] → [extract_candidates]
             → [classify_themes] → [human_review] → [write_back]

Each node is a named, traced unit. Nodes are stubs in this initial scaffolding
issue and will be filled in by subsequent issues.

State flows as a single GraphState dict through all nodes. The graph processes
one full manifest run (batch of documents) per invocation.

Configuration (model names, thresholds, retrieval k) is passed at construction
time via GraphConfig so LLM chains are built once and reused.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, TypedDict

log = logging.getLogger(__name__)

from langgraph.graph import StateGraph, END

from .ingest import IngestedDoc, SkippedDoc, run_ingest
from .retrieve_context import QuestionContext, run_retrieve_context
from .extract_candidates import ThemeCandidate
from .classify_themes import ClassifiedTheme


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class GraphConfig:
    """Per-node model and behavior configuration.

    Model names are set here, not inside node logic. Change the model for a
    node here — no other code changes required.

    These should be revisited with LangSmith evidence after the first real
    runs. The likely path: extract_candidates drops to a cheaper model first
    (relatively mechanical extraction); classify_themes stays on the frontier
    model longest (merge/split judgment is where quality matters most).
    """
    # Judgment-heavy nodes: theme extraction and merge/split decision.
    extract_model: str = "gpt-5.4"
    classify_model: str = "gpt-5.4"
    # Question type classification — may drop to gpt-5-mini with LangSmith evidence.
    question_type_model: str = "gpt-5.4"
    # Embedding model for vector store construction and retrieval queries.
    embedding_model: str = "text-embedding-3-small"
    # Number of similar themes to retrieve per question (per architecture spec: 2-3).
    retrieval_k: int = 3
    # Merge/split confidence below this threshold → flagged for human review.
    review_confidence_threshold: float = 0.4


# ---------------------------------------------------------------------------
# Graph state
#
# TypedDict is the LangGraph convention. All nodes read from and write to this
# shared state dict. Nodes return only the keys they update; the graph merges
# the returned dict into the running state.
#
# Fields typed as list[Any] will be narrowed to specific Pydantic types in
# subsequent issues as those types are defined (ThemeRecord, IngestedDoc, etc.).
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    # --- inputs, set before graph invocation ---
    manifest_docs: list[dict]       # raw docs from manifest JSON (one per meeting note)
    sheet_id: str | None            # Google Sheet ID for output tabs
    run_date: str                   # ISO date string (YYYY-MM-DD); used for tab naming

    # --- loaded from Sheets at run start (Issue #11 / #16) ---
    theme_library: list[Any]        # list[ThemeRecord] — confirmed themes from prior runs
    prior_decisions: list[Any]      # list[ReviewDecision] from prior run's classified notes tab

    # --- ingest output (Issue #10) ---
    ingested_docs: list[IngestedDoc]    # extracted, gate-passed, questions parsed
    skipped_docs: list[SkippedDoc]      # failed the required-field gate

    # --- retrieve_context output (Issue #12) ---
    retrieval_context: list[QuestionContext]  # per-question similar themes from library

    # --- extract_candidates output (Issue #13) ---
    candidates: list[ThemeCandidate]  # proposed sub-topics per question

    # --- classify_themes output (Issue #14) ---
    classified_themes: list[ClassifiedTheme]  # merged/new + question type + topic
    needs_review: list[ClassifiedTheme]       # subset flagged for human review

    # --- run summary, populated by write_back ---
    run_summary: dict               # counts, error list, and any run-level diagnostics


# ---------------------------------------------------------------------------
# Stub nodes
#
# Each node accepts GraphState and returns a dict of the keys it updates.
# Returning {} means "no state changes" — safe for stubs.
# Nodes will be replaced with real implementations in subsequent issues.
# ---------------------------------------------------------------------------

def ingest(state: GraphState) -> dict:
    """Wrap extraction.py; parse follow-up questions into individual items.

    Inputs:  manifest_docs
    Outputs: ingested_docs, skipped_docs
    """
    ingested, skipped = run_ingest(state["manifest_docs"])
    return {"ingested_docs": ingested, "skipped_docs": skipped}


# retrieve_context is built as a closure inside build_graph so it can capture
# the embedding model name and k from GraphConfig without hardcoding them here.
# See _make_retrieve_context_node below.


# extract_candidates is built as a closure inside build_graph so it can capture
# the model name from GraphConfig. See build_graph below.


# classify_themes is built as a closure inside build_graph so it can capture
# model names and the review threshold from GraphConfig. See build_graph below.


def human_review(state: GraphState) -> dict:
    """Separate confident classifications from items flagged for reporter review.

    Inputs:  classified_themes, needs_review
    Outputs: (no state changes — passes through; write_back reads needs_review directly)
    """
    return {}


def write_back(state: GraphState) -> dict:
    """Write classified notes tab and updated theme library tab to Google Sheets.

    Inputs:  classified_themes, ingested_docs, sheet_id, run_date
    Outputs: run_summary

    Skips Sheets output when sheet_id is None (useful for dry runs and tests).
    Theme library tab write is a stub — implemented in a subsequent issue.
    """
    sheet_id = state.get("sheet_id")
    if not sheet_id:
        log.info("write_back: no sheet_id — skipping Sheets output")
        return {"run_summary": {"sheets_written": 0}}

    from .theme_library import build_sheets_client
    from .write_back import write_classified_notes

    sheets = build_sheets_client()
    tab = write_classified_notes(
        state["classified_themes"],
        state["ingested_docs"],
        sheets,
        sheet_id,
        state["run_date"],
    )
    return {"run_summary": {"classified_notes_tab": tab, "sheets_written": 1}}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph(config: GraphConfig | None = None) -> Any:
    """Construct and compile the LangGraph agent graph.

    Args:
        config: model names and behavior thresholds. Defaults to GraphConfig()
                which uses the recommended production settings.

    Returns:
        A compiled LangGraph graph ready for invocation.
    """
    if config is None:
        config = GraphConfig()

    _embedding_model = config.embedding_model
    _retrieval_k = config.retrieval_k
    _extract_model = config.extract_model
    _classify_model = config.classify_model
    _question_type_model = config.question_type_model
    _review_threshold = config.review_confidence_threshold

    def _retrieve_context(state: GraphState) -> dict:
        """Build in-memory vector store from theme_library; retrieve top-k per question.

        Inputs:  ingested_docs, theme_library
        Outputs: retrieval_context

        OpenAIEmbeddings is instantiated lazily — only when the theme library is
        non-empty — so cold-start runs don't require OPENAI_API_KEY. The venue
        context slot is a stub (always empty) per the architecture spec.
        """
        if state["theme_library"]:
            from langchain_openai import OpenAIEmbeddings
            embeddings = OpenAIEmbeddings(model=_embedding_model)
        else:
            embeddings = None

        contexts = run_retrieve_context(
            state["ingested_docs"],
            state["theme_library"],
            embeddings,
            _retrieval_k,
        )
        return {"retrieval_context": contexts}

    def _extract_candidates(state: GraphState) -> dict:
        """LLM: extract one ThemeCandidate per follow-up question.

        Inputs:  retrieval_context
        Outputs: candidates

        ChatOpenAI is instantiated lazily — only when retrieval_context is
        non-empty — so cold-start runs don't require OPENAI_API_KEY.
        """
        if not state["retrieval_context"]:
            return {"candidates": []}

        from langchain_openai import ChatOpenAI
        from .extract_candidates import _ExtractedTheme, run_extract_candidates

        llm = ChatOpenAI(model=_extract_model).with_structured_output(_ExtractedTheme)
        candidates = run_extract_candidates(state["retrieval_context"], llm)
        return {"candidates": candidates}

    def _classify_themes(state: GraphState) -> dict:
        """LLM: merge/split decision, question type, national topic assignment.

        Inputs:  candidates
        Outputs: classified_themes, needs_review

        Two ChatOpenAI instances are created lazily — only when candidates is
        non-empty — so cold-start runs don't require OPENAI_API_KEY.
        """
        if not state["candidates"]:
            return {"classified_themes": [], "needs_review": []}

        from langchain_openai import ChatOpenAI
        from .classify_themes import (
            _MergeSplitDecision,
            _QuestionTypeAndTopic,
            run_classify_themes,
        )

        merge_llm = ChatOpenAI(model=_classify_model).with_structured_output(
            _MergeSplitDecision
        )
        qt_llm = ChatOpenAI(model=_question_type_model).with_structured_output(
            _QuestionTypeAndTopic
        )
        classified, needs_review = run_classify_themes(
            state["candidates"], merge_llm, qt_llm, _review_threshold
        )
        return {"classified_themes": classified, "needs_review": needs_review}

    graph = StateGraph(GraphState)

    graph.add_node("ingest", ingest)
    graph.add_node("retrieve_context", _retrieve_context)
    graph.add_node("extract_candidates", _extract_candidates)
    graph.add_node("classify_themes", _classify_themes)
    graph.add_node("human_review", human_review)
    graph.add_node("write_back", write_back)

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "retrieve_context")
    graph.add_edge("retrieve_context", "extract_candidates")
    graph.add_edge("extract_candidates", "classify_themes")
    graph.add_edge("classify_themes", "human_review")
    graph.add_edge("human_review", "write_back")
    graph.add_edge("write_back", END)

    return graph.compile()
