from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class ClassificationRun:
    manifest: Path
    cutoff_days: int
    total_docs: int
    parseable_docs: int
    needs_review_docs: int
    llm_handoff_docs: tuple[str, ...]
    note: str


@dataclass(slots=True, frozen=True)
class ExtractionRun:
    input_file: Path
    note: str
