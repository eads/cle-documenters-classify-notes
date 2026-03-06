from __future__ import annotations

from dataclasses import dataclass

from .manifest import ManifestDocument
from .quality import ParseQualityAssessment


@dataclass(slots=True, frozen=True)
class LlmHandoffRequest:
    doc_id: str
    handoff_type: str
    prompt_stub: str
    reason_codes: tuple[str, ...]


def build_parse_quality_handoff(
    doc: ManifestDocument,
    assessment: ParseQualityAssessment,
) -> LlmHandoffRequest:
    return LlmHandoffRequest(
        doc_id=doc.doc_id,
        handoff_type="parse_repair",
        prompt_stub=(
            "You are a document normalization assistant. Recover readable text, "
            "preserve tables as markdown, and extract candidate dates."
        ),
        reason_codes=assessment.reasons,
    )
