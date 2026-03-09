from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from .manifest import ManifestDocument

log = logging.getLogger(__name__)


@dataclass
class DedupDecision:
    kept: ManifestDocument
    dropped: list[ManifestDocument]
    reason: str  # "checksum" | "name_containment"


def deduplicate(
    docs: list[ManifestDocument],
) -> tuple[list[ManifestDocument], list[DedupDecision]]:
    """Return (kept_docs, decisions) with duplicates removed, newest wins.

    Two docs are considered duplicates if:
    - Their text_checksum matches (identical content), or
    - They share the same folder_path and one name is a substring of the other.
    """
    kept_after_checksum, checksum_decisions = _dedup_by_checksum(docs)
    kept_final, name_decisions = _dedup_by_name_containment_all(kept_after_checksum)
    return kept_final, checksum_decisions + name_decisions


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dedup_by_checksum(
    docs: list[ManifestDocument],
) -> tuple[list[ManifestDocument], list[DedupDecision]]:
    by_checksum: dict[str, list[ManifestDocument]] = defaultdict(list)
    for doc in docs:
        by_checksum[doc.text_checksum or doc.doc_id].append(doc)

    kept: list[ManifestDocument] = []
    decisions: list[DedupDecision] = []
    for group in by_checksum.values():
        winner = max(group, key=lambda d: d.modified_time or "")
        dropped = [d for d in group if d is not winner]
        if dropped:
            decisions.append(DedupDecision(kept=winner, dropped=dropped, reason="checksum"))
            log.info("checksum dedup: keeping '%s', dropping %s", winner.name, [d.name for d in dropped])
        kept.append(winner)
    return kept, decisions


def _dedup_by_name_containment_all(
    docs: list[ManifestDocument],
) -> tuple[list[ManifestDocument], list[DedupDecision]]:
    by_folder: dict[str, list[ManifestDocument]] = defaultdict(list)
    for doc in docs:
        by_folder[doc.folder_path].append(doc)

    kept: list[ManifestDocument] = []
    decisions: list[DedupDecision] = []
    for folder, folder_docs in by_folder.items():
        folder_kept, folder_decisions = _dedup_folder_by_name(folder_docs, folder)
        kept.extend(folder_kept)
        decisions.extend(folder_decisions)
    return kept, decisions


def _dedup_folder_by_name(
    docs: list[ManifestDocument], folder: str
) -> tuple[list[ManifestDocument], list[DedupDecision]]:
    if len(docs) <= 1:
        return docs, []

    groups: list[set[int]] = []
    for i, a in enumerate(docs):
        matched = False
        for group in groups:
            for j in group:
                b = docs[j]
                if a.name in b.name or b.name in a.name:
                    group.add(i)
                    matched = True
                    break
            if matched:
                break
        if not matched:
            groups.append({i})

    kept: list[ManifestDocument] = []
    decisions: list[DedupDecision] = []
    for group in groups:
        group_docs = [docs[i] for i in group]
        winner = max(group_docs, key=lambda d: d.modified_time or "")
        dropped = [d for d in group_docs if d is not winner]
        if dropped:
            decisions.append(DedupDecision(kept=winner, dropped=dropped, reason="name_containment"))
            log.info(
                "name dedup [%s]: keeping '%s', dropping %s",
                folder, winner.name, [d.name for d in dropped],
            )
        kept.append(winner)
    return kept, decisions
