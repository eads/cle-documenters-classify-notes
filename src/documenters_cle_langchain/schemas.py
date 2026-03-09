from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
