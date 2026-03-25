"""extract_candidates.py — LLM-based theme candidate extraction.

For each follow-up question, produces a ThemeCandidate: proposed sub-topic
label, description, source question verbatim, and the retrieval context that
was provided to the model.

One question → one candidate. This is a deliberate starting constraint.
Genuinely multi-theme questions exist in practice; revisit with LangSmith
evidence after the first real run before relaxing the one-to-one rule.

Called by the `extract_candidates` node in graph.py.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from .retrieve_context import QuestionContext, SimilarTheme

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


class ThemeCandidate(BaseModel):
    """A proposed sub-topic theme extracted from a single follow-up question.

    ``sub_topic`` and ``description`` come from the LLM. All other fields
    are populated by ``run_extract_candidates`` from the input data.
    """

    doc_id: str
    source_question: str        # verbatim follow-up question
    sub_topic: str              # proposed label — specific and lowercase
    description: str            # 1-2 sentence description of the civic concern
    retrieved_context: list[dict]  # SimilarTheme dicts shown to the model as context


# Internal LLM output schema — only the two fields the model generates.
# We add doc_id, source_question, and retrieved_context from the input data.
class _ExtractedTheme(BaseModel):
    sub_topic: str
    description: str


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a civic journalism analyst helping to build a library of recurring \
themes in Cleveland public meeting notes.

A **sub-topic** is a specific, concrete civic issue or concern — narrow enough \
to track over time across multiple meetings. Examples:
  - "Section 8 voucher waitlists" (not "housing")
  - "Magnet school enrollment caps" (not "education")
  - "Lead pipe replacement funding" (not "infrastructure")
  - "Police union contract negotiations" (not "public safety")

Your job: given a follow-up question from a community reporter, propose a \
single sub-topic label and a 1-2 sentence description of the underlying civic \
concern. The label should be specific, lowercase, and suitable as a canonical \
theme name that could recur across meetings."""

USER_PROMPT = """\
Follow-up question from reporter:
"{question}"

{context_section}

Propose a single sub-topic label and a 1-2 sentence description for the civic \
concern expressed in this question. If the question touches multiple issues, \
choose the most specific and actionable one."""


def _format_similar_themes(similar_themes: list[SimilarTheme]) -> str:
    """Format retrieved similar themes as human-readable context lines."""
    if not similar_themes:
        return (
            "No similar themes found in the library — this may be a new sub-topic."
        )
    lines = ["Retrieved similar themes from past meetings:"]
    for i, t in enumerate(similar_themes, 1):
        lines.append(
            f"  {i}. {t['sub_topic']} — {t['description']} ({t['topic']})"
        )
    return "\n".join(lines)


def build_extraction_prompt(
    question: str,
    similar_themes: list[SimilarTheme],
) -> list[dict]:
    """Construct prompt messages for a single question extraction.

    Returns a list of message dicts (system + user). Pure function — no LLM
    call, fully testable without credentials.

    Args:
        question: the follow-up question text.
        similar_themes: retrieved similar themes to show as context.

    Returns:
        ``[{"role": "system", ...}, {"role": "user", ...}]``
    """
    context_section = _format_similar_themes(similar_themes)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_PROMPT.format(
                question=question,
                context_section=context_section,
            ),
        },
    ]


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_extract_candidates(
    retrieval_context: list[QuestionContext],
    llm: Any,  # ChatOpenAI.with_structured_output(_ExtractedTheme), or a test fake
) -> list[ThemeCandidate]:
    """Extract one ThemeCandidate per follow-up question.

    One-to-one: each QuestionContext produces exactly one ThemeCandidate.
    The LLM receives the question text and retrieved similar themes; it returns
    a sub-topic label and description. Metadata (doc_id, source_question,
    retrieved_context) is attached by this function, not by the LLM.

    Args:
        retrieval_context: one QuestionContext per question (from retrieve_context node).
        llm: a LangChain chat model bound to ``_ExtractedTheme`` structured output,
             or a compatible test fake with an ``invoke(messages) -> _ExtractedTheme``
             interface.

    Returns:
        One ThemeCandidate per entry in retrieval_context, in the same order.
    """
    candidates: list[ThemeCandidate] = []

    for ctx in retrieval_context:
        messages = build_extraction_prompt(ctx["question"], ctx["similar_themes"])
        extracted: _ExtractedTheme = llm.invoke(messages)
        candidate = ThemeCandidate(
            doc_id=ctx["doc_id"],
            source_question=ctx["question"],
            sub_topic=extracted.sub_topic,
            description=extracted.description,
            retrieved_context=list(ctx["similar_themes"]),
        )
        candidates.append(candidate)
        log.info(
            "extract_candidates: '%s…' → sub_topic='%s'",
            ctx["question"][:60],
            extracted.sub_topic,
        )

    log.info(
        "extract_candidates: %d questions → %d candidates",
        len(retrieval_context),
        len(candidates),
    )
    return candidates
