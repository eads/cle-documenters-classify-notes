from __future__ import annotations

from .extraction import ExtractedMeeting


def passes_extraction_gate(result: ExtractedMeeting) -> bool:
    """True only when all required fields were extracted successfully."""
    return result.missing_fields == ()
