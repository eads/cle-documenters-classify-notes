from __future__ import annotations

from dataclasses import dataclass

from .manifest import ManifestDocument
from .quality import ParseQualityAssessment
from .schemas import ParseRepairLlmOutput


@dataclass(slots=True, frozen=True)
class LlmHandoffRequest:
    doc_id: str
    handoff_type: str
    output_schema: str
    prompt_stub: str
    reason_codes: tuple[str, ...]


def build_parse_quality_handoff(
    doc: ManifestDocument,
    assessment: ParseQualityAssessment,
) -> LlmHandoffRequest:
    return LlmHandoffRequest(
        doc_id=doc.doc_id,
        handoff_type="parse_repair",
        output_schema=ParseRepairLlmOutput.__name__,
        prompt_stub=(
            "You are a document normalization assistant. Recover readable text, "
            "preserve tables as markdown, and extract candidate dates."
        ),
        reason_codes=assessment.reasons,
    )


def parse_parse_repair_output(payload: object) -> ParseRepairLlmOutput:
    """Validate LLM output against the expected schema."""
    return ParseRepairLlmOutput.model_validate(payload)
