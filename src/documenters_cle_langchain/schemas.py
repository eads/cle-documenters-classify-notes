from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ManifestDocumentInput(BaseModel):
    """Boundary schema for manifest rows loaded from JSON."""

    model_config = ConfigDict(extra="ignore")

    doc_id: str | None = None
    gdoc_id: str | None = None  # Google Docs file ID
    name: str = ""              # file name from Drive
    web_url: str = ""           # Drive webViewLink
    folder_path: str = ""
    modified_time: str = ""     # ISO 8601 from Drive API, used for deduplication
    text: str = ""
    text_checksum: str = ""


class ParseRepairLlmOutput(BaseModel):
    """Expected shape from a parse-repair LLM step."""

    doc_id: str
    normalized_text: str = Field(min_length=1)
    candidate_dates: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str = ""


class NotabilityLlmOutput(BaseModel):
    """Expected shape from a future notability adjudication step."""

    doc_id: str
    important: bool
    importance_score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
