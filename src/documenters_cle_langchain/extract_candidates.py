"""extract_candidates.py — LLM-based theme candidate extraction.

For each follow-up question, produces one or more ThemeCandidates: proposed
sub-topic label(s), description(s), source question verbatim, and the retrieval
context that was provided to the model.

Most questions map to exactly one sub-topic. The LLM may return multiple only
when a question genuinely and distinctly addresses separate civic issues.

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
    sub_topic: str              # proposed label — lowercase, recurring civic issue
    description: str            # 1-2 sentence description of the civic concern
    retrieved_context: list[dict]  # SimilarTheme dicts shown to the model as context


# Internal LLM output schema — one or more sub-topic/description pairs.
# We add doc_id, source_question, and retrieved_context from the input data.
class _SingleTheme(BaseModel):
    sub_topic: str
    description: str


class _ExtractedTheme(BaseModel):
    themes: list[_SingleTheme]


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a civic journalism analyst helping to build a library of recurring \
themes in Cleveland public meeting notes.

A **sub-topic** is a recurring civic issue or concern — specific enough to \
track over time, but abstract enough to recur across multiple Cleveland \
meetings over the course of a year. Examples:
  - "Section 8 voucher waitlists" (not "housing")
  - "Magnet school enrollment caps" (not "education")
  - "Lead pipe replacement funding" (not "infrastructure")
  - "Police union contract negotiations" (not "public safety")

**Right level of abstraction.** Name the underlying civic issue, not the \
specific question or event:
  - Bad: "municipal hiring freeze timeline" (one event) → Good: "municipal staffing and hiring"
  - Bad: "site readiness fund eligibility for vacant industrial properties" → Good: "vacant land redevelopment"
  - Bad: "state authorization for local rent control" → Good: "rent control"
  - Bad: "grant reconciliation reporting transparency" → Good: "budget reporting transparency"

If the question is about a specific bill, fund, or timeline, name the \
underlying civic issue — unless a retrieved theme already tracks that specific \
instance (because a human previously decided it was worth tracking by name).

**Cross-cutting themes.** Some concerns like "transparency" and \
"accountability" span domains — do not add a domain qualifier. A \
transparency concern at a housing meeting and one at a schools meeting \
should both be labeled "transparency", not "housing transparency" and \
"schools transparency".

**Prefer retrieved labels.** If a retrieved theme closely matches the \
underlying issue, use that label. Only create a new label when the question \
is genuinely distinct from all retrieved themes.

**One issue per label — no compound labels.** A sub-topic label names a \
single civic concern. Never combine multiple issues into one label using \
commas or slashes. Bad: "prisons, motherhood and pregnancy" — that is two \
separate sub-topics: "prenatal care in county jails" and "maternal \
reentry support". If a question covers two distinct issues, return two \
separate sub-topic entries.

Your job: given a follow-up question from a community reporter, propose one or \
more sub-topic labels and 1-2 sentence descriptions of the underlying civic \
concerns. Most questions map to exactly one sub-topic — only propose multiple \
if the question genuinely and distinctly addresses separate civic issues. \
Labels should be lowercase and suitable as canonical theme names."""

USER_PROMPT = """\
Follow-up question from reporter:
"{question}"

{context_section}

Propose sub-topic label(s) and description(s) for the civic concern(s) \
expressed in this question. Choose a label that names the underlying civic \
issue — something likely to recur across multiple Cleveland meetings, not a \
summary of this specific question. If a retrieved theme closely matches, \
prefer that label. Most questions have exactly one sub-topic. Only propose \
multiple if the question clearly addresses distinct civic issues that would \
be tracked separately."""


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
    """Extract one or more ThemeCandidates per follow-up question.

    One LLM call per question. The LLM returns a list of sub-topic/description
    pairs (usually one, occasionally more for genuinely multi-issue questions).
    Each pair produces one ThemeCandidate with the same source question and
    retrieved context.

    Args:
        retrieval_context: one QuestionContext per question (from retrieve_context node).
        llm: a LangChain chat model bound to ``_ExtractedTheme`` structured output,
             or a compatible test fake with an ``invoke(messages) -> _ExtractedTheme``
             interface.

    Returns:
        One or more ThemeCandidates per entry in retrieval_context.
    """
    candidates: list[ThemeCandidate] = []

    for ctx in retrieval_context:
        messages = build_extraction_prompt(ctx["question"], ctx["similar_themes"])
        extracted: _ExtractedTheme = llm.invoke(messages)
        for theme in extracted.themes:
            candidate = ThemeCandidate(
                doc_id=ctx["doc_id"],
                source_question=ctx["question"],
                sub_topic=theme.sub_topic,
                description=theme.description,
                retrieved_context=list(ctx["similar_themes"]),
            )
            candidates.append(candidate)
            log.info(
                "extract_candidates: '%s…' → sub_topic='%s'",
                ctx["question"][:60],
                theme.sub_topic,
            )

    log.info(
        "extract_candidates: %d questions → %d candidates",
        len(retrieval_context),
        len(candidates),
    )
    return candidates
