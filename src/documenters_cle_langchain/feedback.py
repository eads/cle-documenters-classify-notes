"""feedback.py — Theme Library derivation from prior Sheets tabs.

Closes the feedback loop between human review decisions and the Theme Library.
Called at the start of each run (load_library node in graph.py) before
retrieve_context builds the vector store.

Two-source derivation:
  1. Most recent theme-overview-YYYY-MM-DD tab → base library (agent-owned)
  2. Most recent classified-notes-YYYY-MM-DD tab → human decisions

apply_decisions is the pure core of this module and is fully testable without
any API credentials.

Decision routing:
  Accept  → confirm theme as-is; increment occurrence and question type count
  Rename  → use corrected_sub_topic as the canonical label; find-or-create
  Reject  → skip; no library change
  Blank   → skip; no action
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

from .theme_library import QuestionType, ThemeRecord, Topic
from .write_back import CLASSIFIED_NOTES_TAB_PREFIX

log = logging.getLogger(__name__)

# Maps question type string values to the corresponding ThemeRecord count field.
_QT_COUNT_FIELD: dict[str, str] = {
    "knowledge_gap": "knowledge_gap_count",
    "process_confusion": "process_confusion_count",
    "skepticism": "skepticism_count",
    "accountability": "accountability_count",
    "continuity": "continuity_count",
}

DECISION_ACCEPT = "Accept"
DECISION_RENAME = "Rename"
DECISION_REJECT = "Reject"


# ---------------------------------------------------------------------------
# ReviewDecision — one row from the classified notes tab
# ---------------------------------------------------------------------------


class ReviewDecision(TypedDict):
    """A single human review decision row from the classified notes tab.

    Contains the agent-assigned fields needed for library derivation, plus
    the reporter-filled decision columns. Blank strings mean no value was
    entered.

    Each agent-assigned field has a corresponding decision column (Accept /
    Reject / Rename) and a corrected-value column used when the decision is
    Rename. All three pairs follow the same pattern.
    """

    source_question: str           # verbatim follow-up question (for representative passage)
    sub_topic: str                 # agent's proposed sub-topic label
    description: str               # agent's sub-topic description (seeds ThemeRecord on creation)
    topic: str                     # agent's proposed national topic
    question_type: str             # agent's assigned question type
    sub_topic_decision: str        # "Accept", "Rename", "Reject", or "" (blank = no action)
    corrected_sub_topic: str       # reporter's corrected label (Rename only)
    topic_decision: str            # "Accept", "Rename", "Reject", or ""
    corrected_topic: str           # reporter's corrected topic (Rename only)
    question_type_decision: str    # "Accept", "Rename", "Reject", or ""
    corrected_question_type: str   # reporter's corrected question type (Rename only)


# ---------------------------------------------------------------------------
# Tab discovery
# ---------------------------------------------------------------------------


def find_latest_classified_notes_tab(tab_titles: list[str]) -> str | None:
    """Return the most recent classified notes tab name, or None if none exist.

    Tab names are ``classified-notes-YYYY-MM-DD``. ISO date strings sort
    lexicographically, so the latest is simply the max.
    """
    tabs = [t for t in tab_titles if t.startswith(CLASSIFIED_NOTES_TAB_PREFIX)]
    if not tabs:
        return None
    return max(tabs)


# ---------------------------------------------------------------------------
# Sheets reader
# ---------------------------------------------------------------------------


def read_classified_notes_decisions(sheets: Any, sheet_id: str) -> list[ReviewDecision]:
    """Read human review decisions from the most recent classified notes tab.

    Returns an empty list on cold start (no classified notes tab exists yet)
    or when the tab contains no data rows.

    Uses header-name column lookup so the function is tolerant of column
    additions or reordering across runs.

    Args:
        sheets: Google Sheets API client (from ``build_sheets_client``).
        sheet_id: the ID of the target spreadsheet.
    """
    metadata = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
    titles = [s["properties"]["title"] for s in metadata.get("sheets", [])]

    tab = find_latest_classified_notes_tab(titles)
    if tab is None:
        log.info("feedback: no classified notes tab found — cold start")
        return []

    log.info("feedback: reading decisions from '%s'", tab)
    result = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"'{tab}'")
        .execute()
    )
    rows = result.get("values", [])
    if len(rows) < 2:
        log.info("feedback: tab '%s' has no data rows", tab)
        return []

    headers = rows[0]
    col = {h: i for i, h in enumerate(headers)}

    def get(row: list, name: str) -> str:
        i = col.get(name)
        if i is None or i >= len(row):
            return ""
        return str(row[i]).strip()

    decisions: list[ReviewDecision] = []
    for row in rows[1:]:
        decisions.append(
            ReviewDecision(
                source_question=get(row, "Source question"),
                sub_topic=get(row, "Sub-topic"),
                description=get(row, "Sub-topic description"),
                topic=get(row, "Topic"),
                question_type=get(row, "Question type"),
                sub_topic_decision=get(row, "Sub-topic decision"),
                corrected_sub_topic=get(row, "Corrected sub-topic"),
                topic_decision=get(row, "Topic decision"),
                corrected_topic=get(row, "Corrected topic"),
                question_type_decision=get(row, "Question type decision"),
                corrected_question_type=get(row, "Corrected question type"),
            )
        )

    log.info("feedback: read %d decision rows", len(decisions))
    return decisions


# ---------------------------------------------------------------------------
# apply_decisions — pure function, no I/O
# ---------------------------------------------------------------------------


def apply_decisions(
    base_library: list[ThemeRecord],
    decisions: list[ReviewDecision],
) -> list[ThemeRecord]:
    """Apply human review decisions to the base Theme Library.

    Pure function — no I/O, fully testable without credentials.

    Starts from the base library (from the prior run's theme overview tab),
    then applies the Accept/Rename/Reject decisions from the most recent
    classified notes tab. Blank-decision rows are skipped.

    Themes in the base library that are not referenced by any decision are
    preserved unchanged.

    When Rename targets an existing theme label, the source passage merges
    into that theme. Question type counts use ``question_type_override`` if
    provided, otherwise the original ``question_type``.

    Args:
        base_library: confirmed themes from the prior run's theme overview tab.
        decisions: human review rows from the most recent classified notes tab.

    Returns:
        Updated list of ThemeRecord objects.
    """
    # Mutable dict keyed by sub_topic so we can find-or-create in O(1).
    library: dict[str, ThemeRecord] = {r.sub_topic: r for r in base_library}

    for dec in decisions:
        decision = dec["sub_topic_decision"].strip().title()

        if not decision or decision == DECISION_REJECT:
            continue

        if decision == DECISION_ACCEPT:
            target_label = dec["sub_topic"]
        elif decision == DECISION_RENAME:
            target_label = dec["corrected_sub_topic"].strip()
            if not target_label:
                log.warning(
                    "feedback: Rename for '%s' has blank corrected_sub_topic — skipping",
                    dec["sub_topic"],
                )
                continue
        else:
            log.warning(
                "feedback: unknown decision '%s' for '%s' — skipping",
                decision,
                dec["sub_topic"],
            )
            continue

        # Resolve topic: use corrected_topic if editor chose Rename, else agent's.
        topic_str = (
            dec["corrected_topic"].strip()
            if dec["topic_decision"].strip().title() == DECISION_RENAME and dec["corrected_topic"].strip()
            else dec["topic"]
        )
        try:
            topic = Topic(topic_str)
        except ValueError:
            topic = Topic.DEVELOPMENT
            log.warning(
                "feedback: unknown topic '%s' for '%s' — defaulting to DEVELOPMENT",
                topic_str,
                target_label,
            )

        # Find or create the target ThemeRecord.
        if target_label not in library:
            library[target_label] = ThemeRecord(sub_topic=target_label, topics=[topic])

        record = library[target_label]
        # Accumulate topics — each question may associate this sub-topic with a
        # different national taxonomy topic (cross-cutting themes appear under
        # multiple topics over time).
        if topic not in record.topics:
            record.topics.append(topic)
        # Seed description from the first decision row that carries one.
        if not record.description and dec["description"]:
            record.description = dec["description"]
        record.occurrence_count += 1
        record.add_passage(dec["source_question"])

        # Increment the appropriate question type count.
        # Use corrected_question_type if editor chose Rename, else agent's.
        effective_qt = (
            dec["corrected_question_type"].strip()
            if dec["question_type_decision"].strip().title() == DECISION_RENAME and dec["corrected_question_type"].strip()
            else dec["question_type"]
        )
        count_field = _QT_COUNT_FIELD.get(effective_qt.strip())
        if count_field:
            setattr(record, count_field, getattr(record, count_field) + 1)

    log.info(
        "feedback: applied %d decisions → library has %d themes",
        len(decisions),
        len(library),
    )
    return list(library.values())
