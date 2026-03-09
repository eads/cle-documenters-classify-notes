from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .schemas import ManifestDocumentInput


@dataclass(slots=True, frozen=True)
class ManifestDocument:
    doc_id: str
    name: str
    web_url: str
    folder_path: str
    modified_time: str
    text: str
    text_checksum: str


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
                name=row.name,
                web_url=row.web_url,
                folder_path=row.folder_path,
                modified_time=row.modified_time,
                text=row.text,
                text_checksum=row.text_checksum,
            )
        )

    return documents
