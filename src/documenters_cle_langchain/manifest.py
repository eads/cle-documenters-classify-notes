from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .schemas import ManifestDocumentInput


@dataclass(slots=True, frozen=True)
class ManifestDocument:
    doc_id: str
    folder_path: str
    text: str


def load_manifest(path: Path) -> list[ManifestDocument]:
    if not path.exists():
        raise FileNotFoundError(f"Manifest file does not exist: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Manifest is not valid JSON: {exc.msg}") from exc

    if not isinstance(payload, list):
        raise ValueError("Manifest must be a JSON array of documents.")

    documents: list[ManifestDocument] = []
    for index, raw in enumerate(payload):
        try:
            row = ManifestDocumentInput.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"Manifest row {index} failed validation: {exc}") from exc

        documents.append(
            ManifestDocument(
                doc_id=row.doc_id or f"row-{index}",
                folder_path=row.folder_path,
                text=row.text,
            )
        )

    return documents
