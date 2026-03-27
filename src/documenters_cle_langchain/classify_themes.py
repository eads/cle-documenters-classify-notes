"""classify_themes.py — Two-inference LLM classification of theme candidates.

For each ThemeCandidate, makes two independent LLM calls:

1. **Merge/split** (classify_model — gpt-5.4): Is this candidate a variant of
   an existing theme in the library (merge) or genuinely new (new)? This is
   the hard judgment step and uses the frontier model. Borderline cases below
   ``review_confidence_threshold`` are marked ``needs_review=True``.

2. **Question type + topic** (question_type_model): Assign one of the five
   epistemic posture labels (or flag low confidence / propose a new type).
   Also assigns the national topic from the 20-topic taxonomy — a constrained
   lookup, not open inference.

The two calls are independent by design. Question type doesn't require
retrieval context; topic assignment is deterministic enough that it can share
a call with question type without confusing the model.

Called by the ``classify_themes`` node in graph.py.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from .extract_candidates import ThemeCandidate
from .retrieve_context import SimilarTheme
from .theme_library import QuestionType, Topic

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Taxonomy reference strings (built once from the enums)
# ---------------------------------------------------------------------------

_QUESTION_TYPE_DEFS = """\
- knowledge_gap: reporter doesn't understand how a process or program works
- process_confusion: reporter doesn't understand how a decision is made or who has authority
- skepticism: a challenge or critique framed as a question, grounded in lived community experience
- accountability: something was promised or required and hasn't happened; asking for follow-through
- continuity: a prior thread hasn't been picked up; reporter is asking what happened next"""

_TOPIC_LIST = "\n".join(f"- {t.value}" for t in Topic)


# ---------------------------------------------------------------------------
# Internal LLM output schemas
# ---------------------------------------------------------------------------


class _MergeSplitDecision(BaseModel):
    """Structured output for the merge/split inference."""

    decision: Literal["merge", "new"]
    matched_theme: str | None   # canonical sub_topic of the existing theme if merge
    confidence: float           # 0.0–1.0
    reasoning: str              # brief explanation; shown in LangSmith trace


class _QuestionTypeAndTopic(BaseModel):
    """Structured output for the combined question-type + topic inference."""

    question_type: str          # one of the 5 taxonomy labels, or "uncertain"
    question_type_confidence: float  # 0.0–1.0
    low_confidence: bool        # True if model flags genuine uncertainty
    proposed_new_type: str | None   # if no existing label fits, describe the new category
    topic: str                  # one of the 20 national taxonomy values


# ---------------------------------------------------------------------------
# ClassifiedTheme — the public output type for this node
# ---------------------------------------------------------------------------


class ClassifiedTheme(BaseModel):
    """A fully classified theme candidate.

    Combines the original ThemeCandidate fields with the results of two
    independent LLM inferences: merge/split and question type + topic.

    ``needs_review`` is True when merge_confidence is below the configured
    threshold — these rows are written to the classified notes tab with the
    Decision column left blank for reporter input.
    """

    # Preserved from ThemeCandidate
    doc_id: str
    source_question: str
    sub_topic: str          # candidate's proposed label (canonical if merge)
    description: str
    retrieved_context: list[dict]

    # Merge/split inference
    decision: Literal["merge", "new"]
    matched_theme: str | None   # existing theme's sub_topic if decision=="merge"
    merge_confidence: float
    merge_reasoning: str
    needs_review: bool          # True if merge_confidence < review_confidence_threshold

    # Question type inference
    question_type: str | None       # None when question_type == "uncertain"
    question_type_confidence: float
    question_type_low_confidence: bool
    proposed_new_question_type: str | None

    # Topic inference
    topic: str                      # national taxonomy value (e.g. "HOUSING")


# ---------------------------------------------------------------------------
# Prompt construction — pure functions, testable without credentials
# ---------------------------------------------------------------------------

_MERGE_SPLIT_SYSTEM = """\
You are classifying whether a proposed civic theme is a variant of an existing \
theme in the Theme Library, or a genuinely new theme.

MERGE: The candidate expresses the same underlying civic concern as an existing \
theme, even if the wording or framing differs. Examples that should merge:
  - "affordable housing voucher delays" → "Section 8 voucher waitlists"
  - "waiting list for rental assistance" → "Section 8 voucher waitlists"

NEW: The candidate expresses a civic concern that is distinct from all retrieved \
themes — a different issue, not just a different phrasing.

When in doubt, lean toward NEW. It is easier for editors to merge themes later \
than to split a theme that was incorrectly merged."""

_MERGE_SPLIT_USER = """\
Candidate theme: "{sub_topic}"
Description: "{description}"

{retrieved_section}

Is this candidate a MERGE with an existing theme, or a NEW theme?
Provide a confidence score (0.0–1.0) and a brief reasoning sentence.
For MERGE, name the existing theme it should merge into (use its exact label)."""

_QT_SYSTEM = """\
You are classifying the epistemic posture of a community reporter's follow-up \
question from a public meeting, and assigning a civic topic category.

**Question type taxonomy:**
{question_type_defs}

These categories can blur in practice — skepticism shades into accountability, \
continuity into accountability. If you are genuinely uncertain between two types, \
set low_confidence=True and pick the closest one. If the question doesn't fit \
any existing category, set proposed_new_type to a short description of what \
new category would fit.

**National topic taxonomy** (pick the single best match):
{topic_list}"""

_QT_USER = """\
Follow-up question: "{question}"
Proposed sub-topic: "{sub_topic}"

Assign a question type and the best-matching national topic."""


def _format_retrieved_themes(similar_themes: list[SimilarTheme]) -> str:
    if not similar_themes:
        return "No similar themes found in the library — this may be a new theme."
    lines = ["Retrieved similar themes from the library:"]
    for i, t in enumerate(similar_themes, 1):
        lines.append(f"  {i}. {t['sub_topic']} — {t['description']} ({t['topic']})")
    return "\n".join(lines)


def build_merge_split_prompt(candidate: ThemeCandidate) -> list[dict]:
    """Construct merge/split prompt messages for a single candidate.

    Pure function — no LLM call, fully testable without credentials.
    """
    retrieved_section = _format_retrieved_themes(
        [SimilarTheme(**t) for t in candidate.retrieved_context]
        if candidate.retrieved_context
        else []
    )
    return [
        {"role": "system", "content": _MERGE_SPLIT_SYSTEM},
        {
            "role": "user",
            "content": _MERGE_SPLIT_USER.format(
                sub_topic=candidate.sub_topic,
                description=candidate.description,
                retrieved_section=retrieved_section,
            ),
        },
    ]


def build_question_type_prompt(candidate: ThemeCandidate) -> list[dict]:
    """Construct question-type + topic prompt messages for a single candidate.

    Pure function — no LLM call, fully testable without credentials.
    """
    return [
        {
            "role": "system",
            "content": _QT_SYSTEM.format(
                question_type_defs=_QUESTION_TYPE_DEFS,
                topic_list=_TOPIC_LIST,
            ),
        },
        {
            "role": "user",
            "content": _QT_USER.format(
                question=candidate.source_question,
                sub_topic=candidate.sub_topic,
            ),
        },
    ]


# ---------------------------------------------------------------------------
# Per-candidate classification
# ---------------------------------------------------------------------------


def classify_one(
    candidate: ThemeCandidate,
    merge_llm: Any,
    qt_llm: Any,
    review_threshold: float,
    tools: list | None = None,
) -> ClassifiedTheme:
    """Run both inferences on a single candidate and return a ClassifiedTheme.

    Args:
        candidate: the ThemeCandidate to classify.
        merge_llm: raw LLM (not pre-bound to structured output).  ``classify_one``
            calls ``bind_tools`` and ``with_structured_output`` internally so that
            tool binding and structured output can be composed correctly.
        qt_llm: raw LLM for question-type + topic inference.
        review_threshold: merge_confidence below this → needs_review=True.
        tools: optional list of LangChain tools to bind to the merge LLM.
            When provided the model may call them before the structured-output
            pass.  The pre-fetched context handles most cases; tools give the
            model on-demand retrieval when it needs more context.
    """
    # Inference 1: merge/split
    # Optional tool-calling pass: bind tools and let the model request additional
    # retrieval context if the pre-fetched context is thin or ambiguous.
    merge_messages: list = list(build_merge_split_prompt(candidate))
    if tools:
        ai_msg = merge_llm.bind_tools(tools).invoke(merge_messages)
        tool_calls = getattr(ai_msg, "tool_calls", None) or []
        if tool_calls:
            merge_messages.append(ai_msg)
            for tc in tool_calls:
                result = next(t for t in tools if t.name == tc["name"]).invoke(tc["args"])
                merge_messages.append(
                    ToolMessage(content=str(result), tool_call_id=tc["id"])
                )
            log.info(
                "classify: tool calls for '%s': %s",
                candidate.sub_topic,
                [tc["name"] for tc in tool_calls],
            )

    # Structured output pass — uses the (possibly tool-augmented) messages.
    merge_dec: _MergeSplitDecision = merge_llm.with_structured_output(
        _MergeSplitDecision
    ).invoke(merge_messages)

    # Inference 2: question type + topic (no tools — taxonomy is fixed)
    qt_messages = build_question_type_prompt(candidate)
    qt_dec: _QuestionTypeAndTopic = qt_llm.with_structured_output(
        _QuestionTypeAndTopic
    ).invoke(qt_messages)

    needs_review = merge_dec.confidence < review_threshold

    # Normalise question type: treat "uncertain" as None
    qt_value = (
        None
        if qt_dec.question_type.lower() == "uncertain"
        else qt_dec.question_type
    )

    classified = ClassifiedTheme(
        doc_id=candidate.doc_id,
        source_question=candidate.source_question,
        sub_topic=candidate.sub_topic,
        description=candidate.description,
        retrieved_context=candidate.retrieved_context,
        decision=merge_dec.decision,
        matched_theme=merge_dec.matched_theme,
        merge_confidence=merge_dec.confidence,
        merge_reasoning=merge_dec.reasoning,
        needs_review=needs_review,
        question_type=qt_value,
        question_type_confidence=qt_dec.question_type_confidence,
        question_type_low_confidence=qt_dec.low_confidence,
        proposed_new_question_type=qt_dec.proposed_new_type,
        topic=qt_dec.topic,
    )

    log.info(
        "classify: '%s' → %s (conf=%.2f%s) | qt=%s | topic=%s",
        candidate.sub_topic,
        merge_dec.decision,
        merge_dec.confidence,
        " REVIEW" if needs_review else "",
        qt_value or "uncertain",
        qt_dec.topic,
    )
    return classified


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_classify_themes(
    candidates: list[ThemeCandidate],
    merge_llm: Any,
    qt_llm: Any,
    review_threshold: float,
    tools: list | None = None,
) -> tuple[list[ClassifiedTheme], list[ClassifiedTheme]]:
    """Classify all candidates and split into full list and needs-review subset.

    Args:
        candidates: ThemeCandidates from extract_candidates node.
        merge_llm: LLM bound to ``_MergeSplitDecision`` structured output.
        qt_llm: LLM bound to ``_QuestionTypeAndTopic`` structured output.
        review_threshold: merge_confidence below this → needs_review=True.

    Returns:
        ``(classified_themes, needs_review)`` — all results, and the subset
        with ``needs_review=True`` for easy state population.
    """
    classified: list[ClassifiedTheme] = []
    for candidate in candidates:
        classified.append(classify_one(candidate, merge_llm, qt_llm, review_threshold, tools=tools))

    needs_review = [c for c in classified if c.needs_review]

    log.info(
        "classify_themes: %d candidates → %d classified, %d flagged for review",
        len(candidates),
        len(classified),
        len(needs_review),
    )
    return classified, needs_review
