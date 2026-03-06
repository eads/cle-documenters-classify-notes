from __future__ import annotations

from pathlib import Path

from .llm_handoff import build_parse_quality_handoff
from .manifest import load_manifest
from .models import ClassificationRun, ExtractionRun
from .quality import ParseQualityGate


class AgentScaffoldApp:
    """Small service layer to keep CLI parsing separate from workflow logic."""

    def classify(self, manifest: Path, cutoff_days: int) -> ClassificationRun:
        docs = load_manifest(manifest)
        quality_gate = ParseQualityGate()
        parseable_docs = 0
        needs_review_docs = 0
        llm_handoff_docs: list[str] = []

        for doc in docs:
            assessment = quality_gate.assess(doc)
            if assessment.status == "parseable":
                parseable_docs += 1
                continue

            needs_review_docs += 1
            handoff = build_parse_quality_handoff(doc=doc, assessment=assessment)
            llm_handoff_docs.append(handoff.doc_id)

        return ClassificationRun(
            manifest=manifest,
            cutoff_days=cutoff_days,
            total_docs=len(docs),
            parseable_docs=parseable_docs,
            needs_review_docs=needs_review_docs,
            llm_handoff_docs=tuple(llm_handoff_docs),
            note=(
                "Scaffold mode: parse-quality gate is active. "
                "Age routing and notability routing are next."
            ),
        )

    def extract(self, input_file: Path) -> ExtractionRun:
        return ExtractionRun(
            input_file=input_file,
            note=(
                "Scaffold mode: extraction sub-agent not implemented yet. "
                "Next step is wiring LangChain extraction for B documents."
            ),
        )
