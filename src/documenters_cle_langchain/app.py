from __future__ import annotations

from pathlib import Path

from .models import ClassificationRun, ExtractionRun


class AgentScaffoldApp:
    """Small service layer to keep CLI parsing separate from workflow logic."""

    def classify(self, manifest: Path, cutoff_days: int) -> ClassificationRun:
        return ClassificationRun(
            manifest=manifest,
            cutoff_days=cutoff_days,
            note=(
                "Scaffold mode: classification pipeline not implemented yet. "
                "Next step is wiring metadata ingestion + routing."
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
