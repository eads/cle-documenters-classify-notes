from __future__ import annotations

import re
from dataclasses import dataclass, field

from dateutil import parser as dateutil_parser
from dateutil.parser import ParserError

# Matches any section heading regardless of # level
_SECTION_RE = re.compile(
    r"^#{0,6}\s*(summary|follow[- ]?up questions?|notes?|single signal)\s*$",
    re.IGNORECASE,
)

# Metadata key: value lines
_META_RE = re.compile(r"^(documenter name|agency|date)\s*:\s*(.+)$", re.IGNORECASE)

# Documenters.org sentinel — marks end of metadata block
_DOCUMENTERS_RE = re.compile(r"documenters\.org", re.IGNORECASE)

# Canonical section names for normalisation
_SECTION_CANONICAL = {
    "summary": "summary",
    "notes": "notes",
    "single signal": "single_signal",
}


def _canonical_section(name: str) -> str:
    n = name.lower().strip()
    if re.match(r"follow[- ]?up questions?", n):
        return "follow_up_questions"
    return _SECTION_CANONICAL.get(n, n)


@dataclass(slots=True, frozen=True)
class ExtractedMeeting:
    doc_id: str
    meeting_name: str
    documenter_name: str
    agency: str
    date_raw: str           # exactly as written in the doc
    date: str | None        # ISO 8601 (YYYY-MM-DD) if parseable, else None
    documenters_url: str
    summary: str
    follow_up_questions: str
    notes: str
    single_signal: str
    confidence: float
    missing_fields: tuple[str, ...]
    method: str = "deterministic"


def extract(doc_id: str, text: str) -> ExtractedMeeting:
    """Deterministic extraction from a meeting note's plain text."""
    lines = text.splitlines()

    # -----------------------------------------------------------------------
    # Pass 1: find the metadata block and locate section boundaries
    # -----------------------------------------------------------------------
    meeting_name = ""
    meta: dict[str, str] = {}
    documenters_url = ""
    sections: dict[str, list[str]] = {}  # canonical_name -> content lines

    current_section: str | None = None
    in_meta = True

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()

        # First non-empty line = meeting name (strip leading #)
        if not meeting_name and line:
            meeting_name = line.lstrip("#").strip()
            continue

        # Look for section heading
        m = _SECTION_RE.match(line)
        if m:
            current_section = _canonical_section(m.group(1))
            sections.setdefault(current_section, [])
            in_meta = False
            continue

        if in_meta:
            # Key: value metadata
            mm = _META_RE.match(line)
            if mm:
                key = mm.group(1).lower().replace(" ", "_")
                meta[key] = mm.group(2).strip()
                continue
            # Documenters.org sentinel
            if _DOCUMENTERS_RE.search(line):
                documenters_url = _extract_url(line)
                in_meta = False
                continue
        elif current_section is not None and line:
            sections[current_section].append(raw_line)

    # -----------------------------------------------------------------------
    # Pass 2: assemble and score
    # -----------------------------------------------------------------------
    agency = re.sub(r"\s*\(https?://[^)]+\)", "", meta.get("agency", "")).strip()
    date_raw = meta.get("date", "")
    date = _parse_date(date_raw)
    documenter_name = meta.get("documenter_name", "")

    summary = _join(sections.get("summary", []))
    follow_up_questions = _join(sections.get("follow_up_questions", []))
    notes = _join(sections.get("notes", []))
    single_signal = _join(sections.get("single_signal", []))

    # Confidence: 4 required fields, each worth 0.25
    required = {"agency": agency, "date": date_raw, "summary": summary, "notes": notes}
    missing = tuple(k for k, v in required.items() if not v)
    confidence = (4 - len(missing)) / 4

    return ExtractedMeeting(
        doc_id=doc_id,
        meeting_name=meeting_name,
        documenter_name=documenter_name,
        agency=agency,
        date_raw=date_raw,
        date=date,
        documenters_url=documenters_url,
        summary=summary,
        follow_up_questions=follow_up_questions,
        notes=notes,
        single_signal=single_signal,
        confidence=confidence,
        missing_fields=missing,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _join(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def _parse_date(raw: str) -> str | None:
    if not raw:
        return None
    try:
        return dateutil_parser.parse(raw, fuzzy=False).date().isoformat()
    except (ParserError, ValueError, OverflowError):
        return None


def _extract_url(line: str) -> str:
    """Pull a bare URL from a line if present, otherwise return the line."""
    m = re.search(r"https?://\S+", line)
    return m.group(0) if m else line.strip()
