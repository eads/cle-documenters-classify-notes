from __future__ import annotations

from dataclasses import dataclass

from .manifest import ManifestDocument


@dataclass(slots=True, frozen=True)
class ParseQualityAssessment:
    doc_id: str
    status: str
    score: float
    reasons: tuple[str, ...]


class ParseQualityGate:
    """Cheap parser-quality checks to avoid wasting downstream compute."""

    def __init__(
        self,
        min_chars: int = 120,
        min_alpha_ratio: float = 0.45,
        max_table_ratio: float = 0.6,
        max_garbled_ratio: float = 0.02,
    ) -> None:
        self.min_chars = min_chars
        self.min_alpha_ratio = min_alpha_ratio
        self.max_table_ratio = max_table_ratio
        self.max_garbled_ratio = max_garbled_ratio

    def assess(self, doc: ManifestDocument) -> ParseQualityAssessment:
        text = doc.text.strip()
        reasons: list[str] = []
        checks = 4
        passed = 0

        if len(text) >= self.min_chars:
            passed += 1
        else:
            reasons.append(f"too_short<{self.min_chars}")

        alpha_ratio = _alpha_ratio(text)
        if alpha_ratio >= self.min_alpha_ratio:
            passed += 1
        else:
            reasons.append(f"low_alpha_ratio<{self.min_alpha_ratio}")

        table_ratio = _table_line_ratio(text)
        if table_ratio <= self.max_table_ratio:
            passed += 1
        else:
            reasons.append(f"high_table_ratio>{self.max_table_ratio}")

        garbled_ratio = _garbled_ratio(text)
        if garbled_ratio <= self.max_garbled_ratio:
            passed += 1
        else:
            reasons.append(f"high_garbled_ratio>{self.max_garbled_ratio}")

        score = passed / checks
        status = "parseable" if score >= 0.75 else "needs_review"

        return ParseQualityAssessment(
            doc_id=doc.doc_id,
            status=status,
            score=score,
            reasons=tuple(reasons) if reasons else ("ok",),
        )


def _alpha_ratio(text: str) -> float:
    if not text:
        return 0.0
    alpha_count = sum(1 for char in text if char.isalpha())
    return alpha_count / len(text)


def _table_line_ratio(text: str) -> float:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0
    table_like = sum(1 for line in lines if "|" in line or "\t" in line)
    return table_like / len(lines)


def _garbled_ratio(text: str) -> float:
    if not text:
        return 0.0
    garbled_chars = "�\x00"
    garbled_count = sum(1 for char in text if char in garbled_chars)
    return garbled_count / len(text)
