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

from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END


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
    ingested_docs: list[Any]        # list[IngestedDoc] — extracted, gate-passed, questions parsed
    skipped_docs: list[Any]         # list[SkippedDoc] — failed the required-field gate

    # --- retrieve_context output (Issue #12) ---
    retrieval_context: list[Any]    # list[QuestionContext] — per-question similar themes from library

    # --- extract_candidates output (Issue #13) ---
    candidates: list[Any]           # list[ThemeCandidate] — proposed sub-topics per question

    # --- classify_themes output (Issue #14) ---
    classified_themes: list[Any]    # list[ClassifiedTheme] — merged/new + question type + topic
    needs_review: list[Any]         # subset of classified_themes flagged for human review

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
    return {}


def retrieve_context(state: GraphState) -> dict:
    """Build in-memory vector store from theme_library; retrieve top-k per question.

    Inputs:  ingested_docs, theme_library
    Outputs: retrieval_context
    """
    return {}


def extract_candidates(state: GraphState) -> dict:
    """LLM: extract candidate sub-topic themes from follow-up questions.

    Inputs:  ingested_docs, retrieval_context
    Outputs: candidates
    """
    return {}


def classify_themes(state: GraphState) -> dict:
    """LLM: merge/split decision, question type, national topic assignment.

    Inputs:  candidates, retrieval_context
    Outputs: classified_themes, needs_review
    """
    return {}


def human_review(state: GraphState) -> dict:
    """Separate confident classifications from items flagged for reporter review.

    Inputs:  classified_themes, needs_review
    Outputs: (no state changes — passes through; write_back reads needs_review directly)
    """
    return {}


def write_back(state: GraphState) -> dict:
    """Write classified notes tab and updated theme library tab to Google Sheets.

    Inputs:  classified_themes, needs_review, theme_library, sheet_id, run_date
    Outputs: run_summary
    """
    return {}


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

    graph = StateGraph(GraphState)

    graph.add_node("ingest", ingest)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("extract_candidates", extract_candidates)
    graph.add_node("classify_themes", classify_themes)
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
