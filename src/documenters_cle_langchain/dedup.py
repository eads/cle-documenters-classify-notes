from __future__ import annotations

import logging
from collections import defaultdict

from .manifest import ManifestDocument

log = logging.getLogger(__name__)


def deduplicate(docs: list[ManifestDocument]) -> list[ManifestDocument]:
    """Return docs with duplicates removed, keeping the most recently modified.

    Two docs are considered duplicates if:
    - Their text_checksum matches (identical content), or
    - They share the same folder_path and one name is a substring of the other
      (same meeting, different version prefixes like "Adam Joseph Copy of ...")

    Within each duplicate group, the doc with the latest modified_time wins.
    """
    # First pass: group by checksum — identical content is trivially deduped
    by_checksum: dict[str, list[ManifestDocument]] = defaultdict(list)
    for doc in docs:
        key = doc.text_checksum or doc.doc_id
        by_checksum[key].append(doc)

    deduped_by_checksum: list[ManifestDocument] = []
    for group in by_checksum.values():
        winner = max(group, key=lambda d: d.modified_time or "")
        if len(group) > 1:
            dropped = [d.name for d in group if d is not winner]
            log.info("checksum dedup: keeping '%s', dropping %s", winner.name, dropped)
        deduped_by_checksum.append(winner)

    # Second pass: within each folder, name-containment dedup
    by_folder: dict[str, list[ManifestDocument]] = defaultdict(list)
    for doc in deduped_by_checksum:
        by_folder[doc.folder_path].append(doc)

    result: list[ManifestDocument] = []
    for folder, folder_docs in by_folder.items():
        result.extend(_dedup_by_name_containment(folder_docs, folder))

    return result


def _dedup_by_name_containment(
    docs: list[ManifestDocument], folder: str
) -> list[ManifestDocument]:
    """Within a folder, merge docs where one name is a substring of another."""
    if len(docs) <= 1:
        return docs

    # Build groups: if name_a is in name_b or vice versa, they're the same meeting
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

    result: list[ManifestDocument] = []
    for group in groups:
        group_docs = [docs[i] for i in group]
        winner = max(group_docs, key=lambda d: d.modified_time or "")
        if len(group_docs) > 1:
            dropped = [d.name for d in group_docs if d is not winner]
            log.info(
                "name dedup [%s]: keeping '%s', dropping %s",
                folder, winner.name, dropped,
            )
        result.append(winner)

    return result
