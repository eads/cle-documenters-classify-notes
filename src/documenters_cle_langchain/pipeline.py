"""
pipeline.py — end-to-end document processing pipeline.

Stages (in order):
    1. Load     — read a fetched manifest JSON into ManifestDocuments
    2. Dedup    — remove duplicate docs (checksum + name-containment, newest wins)
    3. Extract  — deterministic metadata/section extraction from plain text
    4. Gate     — drop docs missing any required field (agency, date, summary, notes)
    5. Classify — LLM civic-infrastructure classifier (summary only, Claude Haiku)

Docs that fail the gate are logged and excluded from classifier input and output.
No LLM repair is attempted on failed extractions.

Output is a PipelineResult containing:
    - results: list of PipelineDoc (one per doc that passed the gate)
    - skipped: list of SkippedDoc (one per doc that failed the gate)
    - counts: summary statistics
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .classifiers import MeetingClassifier, TopicsResult
from .dedup import deduplicate
from .extraction import ExtractedMeeting, extract
from .gate import passes_extraction_gate
from .manifest import ManifestDocument, load_manifest

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


@dataclass
class PipelineDoc:
    """A document that passed all gates and has been fully processed."""
    # --- source ---
    doc_id: str
    name: str
    web_url: str
    folder_path: str
    modified_time: str
    # --- extraction ---
    meeting_name: str
    documenter_name: str
    agency: str
    date: str | None        # ISO 8601
    date_raw: str
    documenters_url: str
    summary: str
    follow_up_questions: str
    notes: str
    single_signal: str
    extraction_confidence: float
    # --- classification ---
    topics: dict  # TopicsResult serialized to dict


@dataclass
class SkippedDoc:
    """A document that failed the extraction gate."""
    doc_id: str
    name: str
    web_url: str
    missing_fields: tuple[str, ...]
    extraction_confidence: float


@dataclass
class PipelineCounts:
    total_after_dedup: int
    passed_gate: int
    skipped: int
    any_topic_match: int
    dedup_decisions: int


@dataclass
class PipelineResult:
    results: list[PipelineDoc]
    skipped: list[SkippedDoc]
    counts: PipelineCounts


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_pipeline(
    manifest_path: Path,
    classifier: MeetingClassifier,
) -> PipelineResult:
    """Load a manifest and run all pipeline stages, returning structured results.

    Args:
        manifest_path: path to a JSON manifest produced by ``fetch``.
        classifier: a configured CivicInfrastructureClassifier instance.
    """
    # Stage 1: Load
    log.info("=== Stage 1: Load ===")
    docs = load_manifest(manifest_path)
    log.info("loaded %d docs from %s", len(docs), manifest_path)

    # Stage 2: Dedup
    log.info("=== Stage 2: Dedup ===")
    docs, dedup_decisions = deduplicate(docs)
    log.info("kept %d docs after dedup (%d removed)", len(docs), len(dedup_decisions))

    # Stage 3 + 4: Extract then gate
    log.info("=== Stage 3+4: Extract + Gate ===")
    passing: list[tuple[ManifestDocument, ExtractedMeeting]] = []
    skipped: list[SkippedDoc] = []

    for doc in docs:
        extraction = extract(doc_id=doc.doc_id, text=doc.text)
        if passes_extraction_gate(extraction):
            passing.append((doc, extraction))
        else:
            log.warning(
                "gate FAIL — skipping '%s' (missing: %s)",
                doc.name, extraction.missing_fields,
            )
            skipped.append(SkippedDoc(
                doc_id=doc.doc_id,
                name=doc.name,
                web_url=doc.web_url,
                missing_fields=extraction.missing_fields,
                extraction_confidence=extraction.confidence,
            ))

    log.info("gate: %d passed, %d skipped", len(passing), len(skipped))

    # Stage 5: Classify
    log.info("=== Stage 5: Classify ===")
    results: list[PipelineDoc] = []

    for i, (doc, extraction) in enumerate(passing, 1):
        log.info("[%d/%d] classifying: %s", i, len(passing), doc.name)
        topics: TopicsResult = classifier.classify(
            meeting_name=extraction.meeting_name,
            agency=extraction.agency,
            summary=extraction.summary,
        )
        results.append(PipelineDoc(
            doc_id=doc.doc_id,
            name=doc.name,
            web_url=doc.web_url,
            folder_path=doc.folder_path,
            modified_time=doc.modified_time,
            meeting_name=extraction.meeting_name,
            documenter_name=extraction.documenter_name,
            agency=extraction.agency,
            date=extraction.date,
            date_raw=extraction.date_raw,
            documenters_url=extraction.documenters_url,
            summary=extraction.summary,
            follow_up_questions=extraction.follow_up_questions,
            notes=extraction.notes,
            single_signal=extraction.single_signal,
            extraction_confidence=extraction.confidence,
            topics=topics.model_dump(),
        ))

    any_match = sum(
        1 for r in results
        if any(v.get("relevant") for v in r.topics.values())
    )
    log.info(
        "=== Done === passed=%d skipped=%d any_topic_match=%d",
        len(results), len(skipped), any_match,
    )

    return PipelineResult(
        results=results,
        skipped=skipped,
        counts=PipelineCounts(
            total_after_dedup=len(docs),
            passed_gate=len(passing),
            skipped=len(skipped),
            any_topic_match=any_match,
            dedup_decisions=len(dedup_decisions),
        ),
    )
