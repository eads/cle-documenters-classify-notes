from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class ManifestDocument:
    doc_id: str
    folder_path: str
    text: str


def load_manifest(path: Path) -> list[ManifestDocument]:
    if not path.exists():
        raise FileNotFoundError(f"Manifest file does not exist: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Manifest must be a JSON array of documents.")

    documents: list[ManifestDocument] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise ValueError(f"Manifest row {index} must be an object.")

        doc_id = str(raw.get("doc_id") or f"row-{index}")
        folder_path = str(raw.get("folder_path") or "")
        text = str(raw.get("text") or "")
        documents.append(ManifestDocument(doc_id=doc_id, folder_path=folder_path, text=text))

    return documents
