"""graph.py — LangGraph agent for meeting note theme extraction and classification.

Graph topology:
    [load_library] → [ingest] → [retrieve_context] → [extract_candidates]
                  → [classify_themes] → [human_review] → [write_back]

Each node is a named, traced unit. State flows as a single GraphState dict
through all nodes. The graph processes one full manifest run (batch of
documents) per invocation.

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
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    # --- inputs, set before graph invocation ---
    manifest_docs: list[dict]       # raw docs from manifest JSON (one per meeting note)
    sheet_id: str | None            # Google Sheet ID for output tabs
    run_date: str                   # ISO date string (YYYY-MM-DD); used for tab naming

    # --- loaded from Sheets at run start by load_library node ---
    theme_library: list[Any]        # list[ThemeRecord] — confirmed themes from prior runs
    prior_decisions: list[Any]      # list[ReviewDecision] from prior run's classified notes tab

    # --- ingest output ---
    ingested_docs: list[IngestedDoc]    # extracted, gate-passed, questions parsed
    skipped_docs: list[SkippedDoc]      # failed the required-field gate

    # --- retrieve_context output ---
    retrieval_context: list[QuestionContext]  # per-question similar themes from library

    # --- extract_candidates output ---
    candidates: list[ThemeCandidate]  # proposed sub-topics per question

    # --- classify_themes output ---
    classified_themes: list[ClassifiedTheme]  # merged/new + question type + topic
    needs_review: list[ClassifiedTheme]       # subset flagged for human review

    # --- run summary, populated by write_back ---
    run_summary: dict               # counts, error list, and any run-level diagnostics


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def load_library(state: GraphState) -> dict:
    """Derive the current run's Theme Library from prior Sheets tabs.

    Reads the most recent theme-overview tab (base library) and the most recent
    classified-notes tab (human decisions). Applies decisions to produce the
    updated library for this run.

    Cold start (no prior tabs) → empty library, no error.
    Dry run (sheet_id=None) → empty library, no Sheets calls.

    Inputs:  sheet_id
    Outputs: theme_library, prior_decisions
    """
    sheet_id = state.get("sheet_id")
    if not sheet_id:
        log.info("load_library: no sheet_id — cold start with empty library")
        return {"theme_library": [], "prior_decisions": []}

    from .feedback import apply_decisions, read_classified_notes_decisions
    from .theme_library import build_sheets_client, read_theme_library

    sheets = build_sheets_client()
    base_library = read_theme_library(sheets, sheet_id)
    decisions = read_classified_notes_decisions(sheets, sheet_id)
    updated_library = apply_decisions(base_library, decisions)

    log.info(
        "load_library: %d base themes + %d decisions → %d themes",
        len(base_library),
        len(decisions),
        len(updated_library),
    )
    return {"theme_library": updated_library, "prior_decisions": decisions}


def ingest(state: GraphState) -> dict:
    """Wrap extraction.py; parse follow-up questions into individual items.

    Inputs:  manifest_docs
    Outputs: ingested_docs, skipped_docs
    """
    ingested, skipped = run_ingest(state["manifest_docs"])
    return {"ingested_docs": ingested, "skipped_docs": skipped}


# retrieve_context, extract_candidates, and classify_themes are built as
# closures inside build_graph so they can capture model names and thresholds
# from GraphConfig without hardcoding them here.


def human_review(state: GraphState) -> dict:
    """Separate confident classifications from items flagged for reporter review.

    Inputs:  classified_themes, needs_review
    Outputs: (no state changes — passes through; write_back reads needs_review directly)
    """
    return {}


def write_back(state: GraphState) -> dict:
    """Write classified notes tab and theme overview tab to Google Sheets.

    Inputs:  classified_themes, ingested_docs, theme_library, sheet_id, run_date
    Outputs: run_summary

    Skips Sheets output when sheet_id is None (dry runs / tests).
    Writes two tabs per run:
      - classified-notes-{run_date}: one row per question, decision columns blank
      - theme-overview-{run_date}: materialized library cache for the next run
    """
    sheet_id = state.get("sheet_id")
    if not sheet_id:
        log.info("write_back: no sheet_id — skipping Sheets output")
        return {"run_summary": {"sheets_written": 0}}

    from .theme_library import build_sheets_client, write_theme_library
    from .write_back import enrich_library_descriptions, write_classified_notes

    sheets = build_sheets_client()
    classified_tab = write_classified_notes(
        state["classified_themes"],
        state["ingested_docs"],
        sheets,
        sheet_id,
        state["run_date"],
    )

    theme_library = state.get("theme_library") or []
    if not theme_library:
        log.info(
            "write_back: theme library is empty — skipping theme-overview tab "
            "(cold start; library will populate after first review cycle)"
        )
        return {
            "run_summary": {
                "classified_notes_tab": classified_tab,
                "theme_overview_tab": None,
                "sheets_written": 1,
            }
        }

    enrich_library_descriptions(theme_library, state.get("classified_themes") or [])

    theme_tab = write_theme_library(
        theme_library,
        sheets,
        sheet_id,
        state["run_date"],
    )
    return {
        "run_summary": {
            "classified_notes_tab": classified_tab,
            "theme_overview_tab": theme_tab,
            "sheets_written": 2,
        }
    }


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

    graph.add_node("load_library", load_library)
    graph.add_node("ingest", ingest)
    graph.add_node("retrieve_context", _retrieve_context)
    graph.add_node("extract_candidates", _extract_candidates)
    graph.add_node("classify_themes", _classify_themes)
    graph.add_node("human_review", human_review)
    graph.add_node("write_back", write_back)

    graph.set_entry_point("load_library")
    graph.add_edge("load_library", "ingest")
    graph.add_edge("ingest", "retrieve_context")
    graph.add_edge("retrieve_context", "extract_candidates")
    graph.add_edge("extract_candidates", "classify_themes")
    graph.add_edge("classify_themes", "human_review")
    graph.add_edge("human_review", "write_back")
    graph.add_edge("write_back", END)

    return graph.compile()
