"""ingest.py — deterministic document ingestion for the LangGraph agent.

Wraps extraction.py and gate.py. Adds follow-up question parsing.
Called by the `ingest` node in graph.py.

No LLM calls. All logic here is deterministic and unit-testable without
any API credentials.
"""
from __future__ import annotations

import logging
import re
from typing import TypedDict

from .extraction import extract
from .gate import passes_extraction_gate

log = logging.getLogger(__name__)

# Strips leading list markers: "1. " "2) " "- " "* " "• "
_MARKER_RE = re.compile(r"^\s*(\d+[\.\)]\s+|[-*•]\s+)")

# Unwraps markdown bold/italic: **text** or *text*
_BOLD_RE = re.compile(r"\*{1,2}(.+?)\*{1,2}")


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


class IngestedDoc(TypedDict):
    """A document that passed the gate, with follow-up questions parsed into a list."""

    # source
    doc_id: str
    name: str
    web_url: str
    folder_path: str
    modified_time: str
    # extraction
    meeting_name: str
    documenter_name: str
    agency: str
    date: str | None        # ISO 8601 if parseable, else None
    date_raw: str
    documenters_url: str
    summary: str
    follow_up_questions: list[str]  # individual questions — primary analysis unit
    notes: str
    single_signal: str
    extraction_confidence: float


class SkippedDoc(TypedDict):
    """A document that failed the required-field gate."""

    doc_id: str
    name: str
    web_url: str
    missing_fields: tuple[str, ...]
    extraction_confidence: float


# ---------------------------------------------------------------------------
# Question parser
# ---------------------------------------------------------------------------


def parse_questions(blob: str) -> list[str]:
    """Parse a follow-up questions blob into a list of individual question strings.

    Handles all formatting variations found in real Documenters notes:
    - Numbered lists (``1. Q`` or ``1) Q``)
    - Bulleted lists (``- Q``, ``* Q``, ``• Q``)
    - Bare lines (each non-empty line becomes a question)
    - Markdown bold (``**Q?**`` → ``Q?``)
    - Mixed formatting within the same section

    A single line with no markers is returned as one question. Multiple
    non-empty lines each become a separate question — splitting on sentence
    boundaries is fragile and is not attempted.

    Args:
        blob: raw text from the follow-up questions section, as returned by
              ``extraction.extract()``.

    Returns:
        List of question strings, stripped of markers and whitespace.
        Empty list if the blob is empty or whitespace-only.
    """
    if not blob.strip():
        return []

    questions = []
    for line in blob.splitlines():
        # Strip leading list markers
        cleaned = _MARKER_RE.sub("", line).strip()
        # Unwrap markdown bold/italic
        cleaned = _BOLD_RE.sub(r"\1", cleaned).strip()
        if cleaned:
            questions.append(cleaned)
    return questions


# ---------------------------------------------------------------------------
# Ingest runner
# ---------------------------------------------------------------------------


def run_ingest(
    manifest_docs: list[dict],
) -> tuple[list[IngestedDoc], list[SkippedDoc]]:
    """Run deterministic extraction and gate check over all manifest docs.

    For each doc: extract structured fields, check required-field gate,
    parse follow-up questions into individual items.

    Args:
        manifest_docs: raw doc dicts from the manifest JSON, as stored in
                       ``GraphState["manifest_docs"]``.

    Returns:
        ``(ingested_docs, skipped_docs)`` — docs that passed the gate, and
        docs that didn't.
    """
    ingested: list[IngestedDoc] = []
    skipped: list[SkippedDoc] = []

    for raw in manifest_docs:
        doc_id = raw.get("doc_id") or raw.get("gdoc_id", "")
        name = raw.get("name", "")
        web_url = raw.get("web_url", "")

        extraction = extract(doc_id=doc_id, text=raw.get("text", ""))

        if not passes_extraction_gate(extraction):
            log.warning(
                "gate fail — skipping '%s' (missing: %s)", name, extraction.missing_fields
            )
            skipped.append(
                SkippedDoc(
                    doc_id=doc_id,
                    name=name,
                    web_url=web_url,
                    missing_fields=extraction.missing_fields,
                    extraction_confidence=extraction.confidence,
                )
            )
            continue

        questions = parse_questions(extraction.follow_up_questions)
        log.debug("  '%s' — %d follow-up question(s) parsed", name, len(questions))

        ingested.append(
            IngestedDoc(
                doc_id=doc_id,
                name=name,
                web_url=web_url,
                folder_path=raw.get("folder_path", ""),
                modified_time=raw.get("modified_time", ""),
                meeting_name=extraction.meeting_name,
                documenter_name=extraction.documenter_name,
                agency=extraction.agency,
                date=extraction.date,
                date_raw=extraction.date_raw,
                documenters_url=extraction.documenters_url,
                summary=extraction.summary,
                follow_up_questions=questions,
                notes=extraction.notes,
                single_signal=extraction.single_signal,
                extraction_confidence=extraction.confidence,
            )
        )

    log.info(
        "ingest: %d docs — %d passed gate, %d skipped",
        len(manifest_docs),
        len(ingested),
        len(skipped),
    )
    return ingested, skipped
