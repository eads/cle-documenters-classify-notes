# HISTORY.md

Append-only log of work completed, decisions made, and things deferred. One entry per issue. Do not edit past entries.

---

## Issue #53 — Theme overview schema: multi-valued topics, drop canonical_form, populate description

**Date:** 2026-03-26

**Branch:** `issue-53-schema-multi-topics-description`

**What was built:**

Three related schema fixes across `theme_library.py`, `write_back.py`, `feedback.py`, and `retrieve_context.py`. No logic restructuring — each change is a targeted fix to a specific gap.

**1. `topics: list[Topic]` replaces `topic: Topic` in `ThemeRecord`**

The old single-valued `topic` field froze the national taxonomy association at first creation. Cross-cutting sub-topics like "transparency" may appear under HOUSING in one meeting and EDUCATION in another — the library now accumulates all observed topics. `apply_decisions` adds the incoming topic to `record.topics` on every Accept/Rename (using `if topic not in record.topics` to prevent duplicates). New records are created with `topics=[topic]`.

`to_row` serializes as a comma-separated string. `from_row` parses "Included in topics" first, then falls back to the old "Topic" column header for backward compat with existing tabs. `retrieve_context.py`'s vector store metadata also updated to join the topics list.

**2. `canonical_form` removed**

Never populated by anything — `apply_decisions` didn't set it, nothing read it. The Rename decision already provides canonical naming by making the corrected label the library key. Removed from `ThemeRecord`, `COLUMNS`, `to_row`, and `from_row`. The `get` helper in `from_row` already tolerates missing columns, so old tabs are unaffected.

**3. "Sub-topic description" added to classified-notes tab; description flows to ThemeRecord**

`ThemeCandidate.description` (produced by extraction) was being silently dropped — `write_back.py` had no column for it, so `ReviewDecision` never carried it and `apply_decisions` could never populate `ThemeRecord.description`. Fixed by:
- Adding "Sub-topic description" to `write_back.COLUMNS` and `build_classified_notes_rows`
- Adding `description: str` to `ReviewDecision` and reading it from "Sub-topic description" in `read_classified_notes_decisions`
- In `apply_decisions`, seeding `record.description` from the first decision row that carries one (existing descriptions are not overwritten)

The same seed-on-first behavior applies on Rename — the renamed-to theme gets the description from the decision row if it has none yet.

**Tests:** 10 new tests covering multi-topic accumulation, no-duplicate topic logic, description seeding, description preservation, backward-compat tab read, and sub-topic description column round-trip. 314 total pass (5 skipped, unchanged).

**Key decisions:**

- **Seed-not-overwrite for description.** On Accept, we don't overwrite an existing description with a new decision row's description. The first human-confirmed description wins. This prevents a later, lower-quality extraction from silently replacing one that a reviewer already implicitly approved.
- **Comma-join for topics display.** The "Included in topics" column stores a comma-separated string (e.g. `"HOUSING, EDUCATION"`). This is human-readable in the sheet, parseable on the way back in, and doesn't require a new column per topic.
- **`retrieve_context.py` metadata.** The vector store metadata `topic` key is now the comma-joined topics string. `_format_retrieved_context` in `write_back.py` already treats it as a display string, so no change needed there.

---

## Issue #47 — Fix sub-topic extraction prompt: recurring labels, not question summaries

**Date:** 2026-03-26

**Branch:** `issue-47-fix-subtopic-specificity`

**What was built:**

Prompt changes only in `extract_candidates.py`. No logic changes.

- Replaced the "specific, concrete" sub-topic framing with "recurring civic issue — specific enough to track, but abstract enough to recur across multiple Cleveland meetings over a year."
- Added four counter-examples in the system prompt showing over-specific → right-level pairs drawn from the issue (e.g. "municipal hiring freeze timeline" → "municipal staffing and hiring"; "grant reconciliation reporting transparency" → "budget reporting transparency").
- Added guidance to name the underlying civic issue when a question is about a specific bill, fund, or timeline — unless a retrieved theme already tracks that specific instance (RAG-established names are preserved).
- Corrected the cross-cutting theme guidance: abstract concepts like "transparency" and "accountability" should NOT carry a domain qualifier — a transparency concern at a housing meeting and one at a schools meeting both get labeled "transparency", not "housing transparency" / "schools transparency".
- Added directive in both system and user prompts to prefer retrieved theme labels when there's a close match.
- Removed "specific" from the label quality description; replaced with "lowercase and suitable as canonical theme names."

6 new prompt-content tests. 304 total pass.

**Key decisions:**

- Cross-cutting vs. domain-specific: the updated issue clarified that abstract concerns ("transparency", "accountability") should share a single cross-domain label. The earlier draft I wrote had this backwards (instructing the model to add domain qualifiers). Corrected before commit.
- RAG exception for specific instances: the owner's comment asked that we preserve named labels for specific bills/funds/initiatives when they were previously named by a human reviewer. The guidance threads this: default to the abstract underlying issue, but defer to a retrieved label when one exists.
- Compound labels (e.g. "prisons, motherhood and pregnancy"): added explicit guidance prohibiting comma-separated compound labels. The model already supports returning multiple `_SingleTheme` entries per question (from Issue #44); it just needed to be told to use that path rather than packing multiple issues into one label. Added a hard-case test using the prisons/maternal example showing the correct output is two separate candidates with no commas in either label.

---

## Issue #46 — Case-insensitive decision matching in feedback.apply_decisions

**Date:** 2026-03-26

**Branch:** `issue-46-case-insensitive-decisions`

**What was built:**

One-line fix in `apply_decisions`: `.strip().title()` normalises the incoming decision value before comparison, so `"RENAME"`, `"rename"`, and `"Rename"` all route correctly. Previously `"RENAME"` fell through to the unknown-decision warning and was silently skipped.

5 new tests covering `ACCEPT`/`RENAME`/`REJECT` in uppercase and `accept`/`rename` in lowercase. 299 total pass.

**Key decisions:**

- `.title()` is the right normaliser here: decision values are single title-case words, so `.title()` converts any casing to the canonical form without affecting anything else. `.lower()` would require changing the constants or comparisons; `.title()` requires no other changes.

---

## Issue #44 — Support multiple sub-topics (and output rows) per question

**Date:** 2026-03-26

**Branch:** `issue-44-multiple-subtopics`

**What was built:**

Changed `extract_candidates.py` from a one-to-one (question → candidate) model to one-to-many (question → 1+ candidates).

- New internal schema: `_SingleTheme(sub_topic, description)` and `_ExtractedTheme(themes: list[_SingleTheme])`. One LLM call per question; the model returns a list of sub-topic/description pairs.
- `run_extract_candidates` now flattens: each `_SingleTheme` in the response produces one `ThemeCandidate`. Shared fields (`doc_id`, `source_question`, `retrieved_context`) are stamped on all candidates from the same question.
- Prompts updated: "propose one or more sub-topic labels" with an explicit note that most questions map to exactly one — only split when the question genuinely addresses distinct civic issues.

Tests: replaced the one-to-one hard-case test with three new tests proving that a two-theme response from a single LLM call produces two candidates sharing `source_question`, `doc_id`, and `retrieved_context`. `test_at_least_one_candidate_per_question` (≥ N) replaces the old exact-count test. 31 tests in the file; 294 total pass.

**Key decisions:**

- **One LLM call per question, not one call per candidate.** Splitting into multiple calls would be wasteful and inconsistent — the model has all the context it needs for a single question in one prompt. The list structure in the response schema handles the multi-topic case naturally.

- **Prompts discourage over-splitting.** "Most questions have exactly one sub-topic" is stated explicitly in both the system and user messages. Without this guardrail, the model might split anything remotely compound.

- **No downstream changes needed.** `classify_themes` consumes a `list[ThemeCandidate]` with no assumption about how many candidates came from the same question. The write-back step writes one row per `ClassifiedTheme`, so multi-topic questions already produce multiple rows naturally.

**Deferred:**

- Sub-topic prompt specificity: user noted prompts are "way too specific" but wants to see RAG results from a real run before adjusting. No prompt changes made beyond the one-to-many framing.

---

## Issue #23 — text_extract.py: preserve hyperlink URLs from Google Docs

**Date:** 2026-03-26

**Branch:** `issue-23-preserve-hyperlinks`

**What was built:**

`_run_text(elem)` helper in `text_extract.py`. Checks `textStyle.link.url` on each paragraph element. When a linked run has non-blank anchor text, emits `anchor text (url)`. Bare text runs and runs with blank anchor text are returned as-is.

`_paragraph` now calls `_run_text` instead of inlining `elem.get("textRun", {}).get("content", "")`.

4 new tests in `test_text_extract.py` using a `_linked_paragraph` fixture helper that builds paragraphs with mixed linked and plain runs. 292 total pass.

**Key decisions:**

- **`content.strip()` guards the URL append.** A linked run with blank or whitespace-only anchor text (e.g. a link on an empty formatting run) does not emit a bare `(url)` in the output. This keeps the text clean for runs that exist for styling rather than content.

- **`content.rstrip("\n")` before appending.** The paragraph-terminal `\n` that Google Docs injects into the last run would otherwise produce `text\n (url)`. Stripping it per-run before appending avoids the issue without changing the existing end-of-paragraph `rstrip("\n")` on the assembled text.

---

## Issue #39 — Classified notes column order, renames, numeric QT confidence

**Date:** 2026-03-26

**Branch:** `issue-39-column-order`

**Also fixes:** Issue #41 (test failing without `OPENAI_API_KEY`)

**What was built:**

Rearranged and renamed the classified notes tab columns. Changes to `write_back.py` only — `feedback.py` uses header-name lookup and does not read any of the renamed columns, so no changes there.

**New column order:**
Meeting date | Meeting body | Source question | Topic | Sub-topic | Sub-topic confidence | Decision | Corrected sub-topic | Question type | Proposed new question type | Question type override | Question type confidence | Notes | Needs review | GDoc URL | Retrieved similar themes

**Renames:**
- `Confidence` → `Sub-topic confidence` (float, unchanged behavior)
- `Question type: low confidence` (yes/"" flag) → `Question type confidence` (float from `ClassifiedTheme.question_type_confidence`)
- `Doc URL` → `GDoc URL`

**Structural changes:**
- Decision columns (`Decision`, `Corrected sub-topic`, `Proposed new question type`, `Question type override`, `Notes`) now grouped together in the middle.
- Triage / reference columns (`Needs review`, `GDoc URL`, `Retrieved similar themes`) moved to the end.
- `Question type` moved into the decision block (adjacent to its override and proposed-new columns).

**Issue #41 fix:** `test_write_back_writes_theme_tab_when_library_populated` failed without `OPENAI_API_KEY` because a populated theme library causes `retrieve_context` to construct `OpenAIEmbeddings`. Patching `langchain_openai.OpenAIEmbeddings` in the test prevents the constructor from reading the environment. Added a comment explaining why. 278 tests pass, 5 integration stubs skip.

**Key decisions:**

- **`question_type_confidence` float replaces the boolean flag.** The boolean was derived from `question_type_low_confidence OR proposed_new_question_type`, which lost information. Using `ClassifiedTheme.question_type_confidence` directly gives reporters a sortable score. `proposed_new_question_type` remains a blank decision column for reporters to fill in.

- **`feedback.py` unchanged.** It reads columns by name and does not touch any of the renamed columns (`Confidence`, `Doc URL`, `Question type: low confidence`).

**Deferred:**

- Pre-filling `Proposed new question type` with the model's suggestion (`theme.proposed_new_question_type`) when one exists — deferred until after the first real run to decide whether that's useful or confusing.

---

## Issue #38 — Tab names: incremental version suffix

**Date:** 2026-03-26

**Branch:** `issue-38-tab-versioning`

**What was built:**

Tab names now include a zero-padded three-digit version suffix:

- `classified-notes-2026-03-26-001`, `classified-notes-2026-03-26-002`, …
- `theme-overview-2026-03-26-001`, `theme-overview-2026-03-26-002`, …

`next_classified_notes_tab_name(run_date, existing_titles)` replaces `classified_notes_tab_name(run_date)` in `write_back.py`. `next_theme_tab_name(run_date, existing_titles)` replaces `theme_tab_name(run_date)` in `theme_library.py`. Both are pure functions: they count existing tabs matching the `{prefix}{date}-` pattern and increment.

`write_classified_notes` and `write_theme_library` each call `spreadsheets().get()` to fetch existing tab titles before creating the new tab. `find_latest_classified_notes_tab` and `find_latest_theme_tab` are unchanged — lexicographic `max()` already handles the new format correctly (`-003` > `-002`, later date beats any suffix).

10 new tests across `test_write_back.py`, `test_theme_library.py`, and `test_feedback.py`. 289 total pass.

**Key decisions:**

- **Version is determined at write time, not passed in.** The write functions query Sheets for existing tabs and compute the next version. This keeps the caller interface simple (run_date only) and avoids passing state the caller shouldn't need to track.

- **Pure naming functions, I/O in the write functions.** `next_*_tab_name` are pure and testable without credentials. All Sheets I/O remains in `write_classified_notes` / `write_theme_library`.

- **No `find_latest_*` changes needed.** The new suffix format sorts correctly with lexicographic `max()` — a later date always beats a higher version on an earlier date, and higher versions on the same date sort correctly.

---

## Issue #34 — Skip writing empty theme-overview tab on cold start

**Date:** 2026-03-26

**Branch:** `issue-34-skip-empty-theme-overview`

**What was built:**

`write_back` in `graph.py` now checks whether `theme_library` is empty before calling `write_theme_library`. On cold start (empty library), it logs a message and skips the write. The `run_summary` reflects the actual count: `sheets_written: 1` and `theme_overview_tab: None`.

Two new tests in `test_graph.py`:
- `test_write_back_skips_theme_tab_on_cold_start` — asserts `write_theme_library` is not called and `theme_overview_tab` is `None` when the library is empty.
- `test_write_back_writes_theme_tab_when_library_populated` — asserts `write_theme_library` is called exactly once and `sheets_written == 2` when the library has records.

279 tests pass, 5 integration stubs skip.

**Key decisions:**

- **Option A chosen: skip the write entirely.** `load_library` already handles "no theme tab found" cleanly on cold start — it logs "cold start" and returns an empty library without error. Writing a header-only tab would confuse operators (can't tell if something went wrong vs. normal cold-start behavior). The classified-notes tab is sufficient evidence that the run happened.

- **The open question ("is the tab useful as a timestamp?") is deferred.** The issue flagged this as "no right answer is obvious — flag for a real run to decide." After the first bootstrapping run, if operators want a run-timestamp artifact independent of classified-notes, a lightweight option is to write a single-row tab with just the run date. Not implemented now.

**Deferred:**

- Run-timestamp artifact separate from classified-notes tab — deferred until after the first real run, when operator workflow is clearer.

---

## Issue #18 — CLI and GitHub Actions: wire new graph, remove old pipeline

**Date:** 2026-03-25

**Branch:** `issue-18-cli-github-actions`

**What was built:**

`cli.py pipeline` now invokes the LangGraph graph instead of the old `pipeline.py` / `classifiers.py` path. The command signature is simpler:

```
uv run documenters-cle-langchain pipeline \
    --manifest /tmp/manifest.json \
    --out /tmp/results.json \
    --sheet-id $SHEET_ID
```

Removed flags: `--model`, `--fallback-model`, `--csv-out`, `--year`, `--month`, `--impersonate`. Added: `--run-date` (optional, defaults to today's ISO date). The graph handles model selection via `GraphConfig`; Sheets tab names are derived from `run_date`.

The handler builds a `GraphState` from the manifest and invokes `build_graph().invoke(state)`. Run summary is written to `--out` as a small JSON diagnostic (counts, `run_summary` from `write_back`). Primary output goes to Sheets when `--sheet-id` is set.

`pipeline.py` and `classifiers.py` deleted. No legacy wrappers.

`gsheets.py` — `_score_label` imported `AMBIGUOUS_LO` / `AMBIGUOUS_HI` from `classifiers.py`. Inlined the constants (`0.3` / `0.7`) directly in `gsheets.py`. The `upload` CLI command and its `gsheets.py` helper are still present — they serve a different purpose (re-uploading a historical results JSON) and were not in scope for removal.

`classify.yml` — three changes:
1. Removed `--year` / `--month` flags from the pipeline step. Tab naming is now driven by `--run-date` (or today's date by default).
2. Added LangSmith env vars: `LANGSMITH_TRACING`, `LANGSMITH_ENDPOINT`, `LANGSMITH_API_KEY` (from secret), `LANGSMITH_PROJECT` (from secret).
3. Added `Clean up credentials` step (`if: always()`) to remove `/tmp/credentials.json` after the job, regardless of success or failure.

`.env.example` already had all LangSmith vars documented — no change needed.

276 tests pass, 5 integration stubs skip.

**Key decisions:**

- **Kept `gsheets.py` and `test_gsheets.py` as-is.** The `upload` command still uploads old-format results to Sheets and `gsheets.py` serves it. Removing it is out of scope for this issue.

- **`--run-date` defaults to today.** The old interface used `--year` / `--month` to build a tab title. The new graph uses an ISO date. For the `classify.yml` workflow, we just let it default to the date the workflow runs — which is what we want.

- **LangSmith secrets are `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT`.** Matches the `.env.example` naming convention (the `LANGSMITH_*` prefix is the modern SDK convention; `LANGCHAIN_*` also works but is legacy).

**Deferred:**

- The `upload` command and `gsheets.py` are now dead weight (the new graph writes to Sheets directly). They can be cleaned up in a future issue once we confirm the new pipeline is stable in production.

- The `--csv-out` flag is gone. If CSV export is needed later, it can be added as a post-processing step reading the classified notes tab from Sheets.

---

## Issue #17 — End-to-end fixture tests

**Date:** 2026-03-25

**Branch:** `issue-17-e2e-fixture-tests`

**What was built:**

Five fixture files in `tests/fixtures/`, each derived from a real Signal Cleveland Documenters note. Each fixture was chosen to cover a specific hard case:

- `fixture_no_questions.txt` — Urban Forestry Budget Committee (Jan 2026). No Follow-Up Questions section. Tests the graceful empty path: full graph runs without LLM calls.
- `fixture_single_question.txt` — Cleveland City Council Health, Human Services and Arts Committee (Jan 2026). One question with skepticism/accountability ambiguity. Tests question type edge cases once integration tests are implemented.
- `fixture_inline_editor_note.txt` — Cuyahoga County Council (Mar 2025). Editor's note inline in the first question (`[Editor's note: The City of Cleveland is one partner...]`). Tests that inline editorial annotations survive question parsing. The Browns stadium question also spans DEVELOPMENT + BUDGET + POLITICS topics.
- `fixture_land_bank.txt` — Cuyahoga County Land Bank Board (Mar 2025). Three questions spanning governance, housing policy, and legal context. Notes section opens with a URL (`Agenda: https://...`), testing the extraction module's tolerance for URLs in the notes body.
- `fixture_public_safety.txt` — Public Safety Technology Advisory Committee (Sep 2024). Three questions with accountability/continuity overlap. Tests question type classification edge cases once integration tests are implemented.

`tests/conftest.py` — auto-skips integration tests when `OPENAI_API_KEY` is absent. Uses `pytest_collection_modifyitems` so the skip is applied at collection time without requiring the `@pytest.mark.skipif` boilerplate on every test.

`pyproject.toml` — updated integration marker description to mention LLM APIs alongside Google APIs, since that is now the primary guard.

`tests/test_e2e.py` — 12 CI tests (no LLM), 5 integration stubs (marked `# TK: integration`).

CI tests cover:
- Each fixture passes or fails the ingest gate as expected (all 5 pass).
- Parsed question counts match the fixture content (0, 1, 3, 3, 3).
- Inline editor's note survives question parsing intact.
- Agency, ISO date, and meeting name extracted correctly from the Health fixture.
- Full graph on the no-questions fixture completes without LLM calls.
- Full graph on empty manifest completes without LLM calls.

Integration stubs are skeleton tests with `pytest.skip("TK: integration — not yet implemented")`. They will be fleshed out after the first real run when OPENAI_API_KEY is available.

**Key decisions:**

- **Only the no-questions fixture can drive a full CI graph run.** With the current graph topology, any question in `retrieval_context` causes `_extract_candidates` to instantiate `ChatOpenAI`. The Urban Forestry fixture has no follow-up questions, so `retrieval_context` is empty and `extract_candidates` short-circuits before touching the OpenAI API. All other fixtures require real LLM calls to exercise beyond ingest.

- **Fixture content includes editor's notes verbatim.** The inline `[Editor's note: ...]` in the County Council fixture is preserved in the question text by design — it provides real context for the LLM. The CI test asserts it survives; the integration test (stub) will verify the LLM handles it gracefully.

- **Fixtures are trimmed but realistic.** Very long Notes sections were shortened to keep fixtures manageable, but the section structure, metadata, and full Follow-Up Questions sections are unmodified from the real Google Docs exports. The hard-case content (inline notes, cross-topic questions, URL in Notes) is preserved exactly as exported.

**Deferred:**

- Integration test bodies: stubs only. Will be implemented once we have an OPENAI_API_KEY in the test environment and have run the pipeline at least once.

- The City Council HEAP Winter Crisis fixture (one very long question) was not included. It's a valid hard case (question longer than a sentence with nested sub-questions) but the five fixtures already cover the scope of this issue. Can be added when integration tests are implemented.

---

## Issue #16 — Human review feedback: read decisions, update Theme Library

**Date:** 2026-03-25

**Branch:** `issue-16-human-review-feedback`

**What was built:**

`feedback.py` — closes the feedback loop between human review decisions and the Theme Library.

`ReviewDecision` TypedDict: the fields extracted from each classified notes row needed for library derivation — source question, sub-topic, topic, question type, decision, corrected sub-topic, and question type override.

`find_latest_classified_notes_tab(tab_titles)` — same pattern as `find_latest_theme_tab`; ISO date suffixes sort lexicographically.

`read_classified_notes_decisions(sheets, sheet_id)` — reads the most recent classified notes tab. Column-tolerant (header-name lookup). Cold start (no tab exists) returns empty list cleanly.

`apply_decisions(base_library, decisions)` — pure function, the testable core. Takes the base library from the prior theme overview tab and a list of decisions from the most recent classified notes tab. Routes:
- **Accept**: find or create theme by `sub_topic`; increment occurrence count and question type count; add source question as representative passage.
- **Rename**: use `corrected_sub_topic` as the canonical label. If that label exists in the library, merge into it. If not, create a new `ThemeRecord`. The original (wrong) label is not added.
- **Reject**: skip. Neither the theme nor any count is modified.
- **Blank / unknown**: skip.

`question_type_override` takes precedence over the agent-assigned `question_type` when incrementing counts, per the issue spec.

`graph.py` — two changes: (1) `load_library` is now the entry node. It derives the theme library before `retrieve_context` runs, so the vector store is built from the most current confirmed themes. With `sheet_id=None` (dry runs, tests), it returns an empty library without hitting Sheets. (2) `write_back` now writes both the classified notes tab and the theme overview tab per run. The theme overview tab is the materialized cache the next run reads as its base library.

`theme_library.py` — `ThemeRecord.description` now defaults to `""`. Themes bootstrapped from Accept/Rename decisions in `apply_decisions` don't have a description available (it's not in the classified notes tab). Empty string is the right placeholder; the embedding will be `"{sub_topic}: "` which is less informative but functional. Editors can refine descriptions in the theme overview tab if needed.

30 new tests in `test_feedback.py`. 264 total tests pass.

**Key decisions:**

- **`apply_decisions` is a pure function, not a Sheets call.** The derivation logic is fully testable without credentials. Sheets I/O is isolated to `read_classified_notes_decisions` and the graph's `load_library` node. Same pattern as `build_classified_notes_rows` in `write_back.py`.

- **Rename does not carry the original label forward.** When a reporter renames "bad label" → "correct label", only "correct label" appears in the updated library. The original is not added, not rejected, not tracked. Its occurrence count is attributed to "correct label".

- **Unknown topic strings fall back to DEVELOPMENT with a warning.** Topic values come from the agent's classified notes output and should always be valid taxonomy strings. The fallback handles the theoretical case without crashing. DEVELOPMENT is a reasonable default (covers the widest civic ground) and the warning makes it visible in logs.

- **`load_library → ingest` topology.** `load_library` and `ingest` are independent — they could run in parallel. Sequential is simpler, and load_library is fast (one or two Sheets API calls). Parallelism isn't worth the complexity here.

**Deferred:**

- The open question from the issue ("When Rename merges into an existing theme, which question type wins?") is resolved as: the new source passage contributes a count to the existing distribution; no override. Implemented as specified.

---

## Issue #15 — write_back node: classified notes tab output

**Date:** 2026-03-25

**Branch:** `issue-15-write-back-classified-notes`

**What was built:**

`write_back.py` — the classified notes tab writer. Two public functions:

`build_classified_notes_rows(classified_themes, ingested_docs) → list[list]` — pure function. Joins each `ClassifiedTheme` to its source `IngestedDoc` on `doc_id` to populate meeting date and body. Builds the full row list (header + one data row per theme). No Sheets dependency; fully testable without credentials.

`write_classified_notes(classified_themes, ingested_docs, sheets, sheet_id, run_date) → str` — Sheets I/O. Creates tab `classified-notes-{run_date}`, writes the rows.

15-column schema: 10 agent-filled (`Meeting date`, `Meeting body`, `Source question`, `Sub-topic`, `Topic`, `Retrieved similar themes`, `Confidence`, `Needs review`, `Question type`, `Question type: low confidence`) + 5 blank reporter decision columns (`Decision`, `Corrected sub-topic`, `Question type override`, `Proposed new question type`, `Notes`).

`graph.py` `write_back` stub replaced with real implementation. Skips Sheets output when `sheet_id` is None (useful for dry runs and tests that don't need Sheets output). Theme library tab write remains a stub — that's a separate issue.

34 new tests in `test_write_back.py`. 234 total tests pass.

**Key decisions:**

- **Dedicated `Needs review` column, not a mixed-type `Confidence` column.** The issue suggested using the confidence column with a "low" string value. Instead: `Confidence` is always a numeric float (for sorting); `Needs review` is "yes"/"" (for filtering). Mixing types in a column is awkward in Sheets and makes filtering harder. Two columns is cleaner.

- **`Retrieved similar themes` as human-readable numbered lines.** Each entry formatted as `"{n}. {sub_topic} — {description} ({topic})"`, joined by newlines. Caps at 3 per question (matching the architecture spec). Returns empty string on cold start. The issue spec called this the most important column — keeping it readable without documentation was the primary constraint.

- **Free text for reporter decision columns.** Dropdown validation (via Sheets batchUpdate) deferred per issue guidance. Adds API complexity for bootstrapping; free text is adequate.

- **`doc_id` join, not embedding metadata in `ClassifiedTheme`.** `ClassifiedTheme` carries only `doc_id`, not the full meeting metadata. `build_classified_notes_rows` does a dict lookup against `ingested_docs`. Missing `doc_id` (shouldn't happen in normal operation) silently produces blank meeting fields rather than raising.

- **`test_graph_passes_through_sheet_id` updated.** This test passed a real-looking sheet_id as a pass-through check when `write_back` was a stub. Now that `write_back` is real, passing a non-None `sheet_id` triggers Sheets API calls. The test was updated to patch `build_sheets_client` and `write_classified_notes` — the pass-through assertion itself is unchanged.

**Deferred:**

- Theme library tab write in `write_back` — a stub in `graph.py`. Implemented in a subsequent issue.
- Dropdown data validation for reporter decision columns — deferred until bootstrapping is complete.

---

## Project genesis — existing codebase

**Date:** 2026

**Repo:** `documenters-cle-langchain` (target name: `documenters-note-classifier`)

**What exists:**

A working end-to-end pipeline that proves the infrastructure: Google Drive → classifier → Google Sheets → GitHub Actions. The hard plumbing is done and tested. What's missing is the brain — LangGraph, LangSmith, RAG, and the full two-level classification scheme described in `ARCHITECTURE.md`.

**Drive reader:** Walks a folder hierarchy of `year / month / note docs`. Handles duplicated docs by reading the latest version. Accepts open suggestions as canonical. This works and is not a priority to change.

**Classifier:** Two LLM calls — a `gpt-5-mini` call that escalates to a `gpt-5.4` call if classification is ambiguous. Currently classifies each note document (not individual follow-up questions) as infrastructure-related, school-related, or both. This is the heart of the system and is what gets ripped out and replaced with the LangGraph agent described in `ARCHITECTURE.md`. The escalation pattern is worth preserving as inspiration for the confidence-routing logic in `classify_themes`.

**Sheets output:** One tab per run, one row per classified document. The schema will need to expand to two tabs per run (classified notes + theme library) as described in `ARCHITECTURE.md`. The existing single-tab approach is a known limitation, not a bug — defer the schema migration until the new classifier is in place.

**Tests:** A couple dozen tests with aggressive coverage intent. Includes classifier tests and integration tests. These are a real asset — the migration to LangGraph should keep them green throughout, not treat them as throwaway scaffolding.

**What this codebase is not:** It does not use LangGraph or LangSmith. It does not have a Theme Library or RAG retrieval. It does not classify at the follow-up question level. It does not implement the two-level sub-topic / question type scheme. All of that is the target state described in `ARCHITECTURE.md`.

**Key decisions made before issue backlog:**

- The escalation pattern in the existing classifier (cheap model → expensive model on ambiguity) maps naturally onto the `classify_themes` node's confidence routing. Preserve this intuition.
- Existing tests are the regression harness for the migration. The first LangGraph issues should keep them passing.
- The Drive reader and Sheets writer are not being replaced — they're the stable boundaries that get wrapped in thin abstractions so the new agent layer can be tested without hitting real APIs.
- Frontier models from the start for the new classifier — bad classifications corrupt the Theme Library and burn human review time. Optimize later with LangSmith evidence.
- Question type taxonomy (`knowledge gap`, `process confusion`, `skepticism`, `accountability`, `continuity`) is a hypothesis to be tested during bootstrapping. Model should flag low confidence rather than force a pick.

**Deferred:**
- Meeting/Venue Knowledge Base (requires human curation, no bootstrap path from notes).
- Real API integration tests beyond what already exists (after first real run with new classifier).
- Promotion from bootstrapping (new tab per run) to stable (append-only canonical tab).
- Airtable or database replacement for Google Sheets (if project receives further investment).
- Rename repo to `documenters-note-classifier` (whenever it feels right).

**Open questions at migration start:**
- Does narrative notes context actually improve extraction quality over follow-up questions alone? LangSmith will tell us.
- Will the question type taxonomy hold against real data, or will categories need splitting/merging during bootstrapping?
- What's the right confidence threshold for routing to human review vs. auto-accepting?
- How much of the existing classifier test suite translates directly to the new node structure vs. needs to be rewritten?

---

## Issue #9 — LangGraph scaffold: state schema, graph topology, LangSmith config

**Date:** 2026-03-24

**Branch:** `issue-9-langgraph-scaffold`

**What was built:**

`graph.py` — the LangGraph skeleton that all subsequent issues will fill in.

`GraphConfig` dataclass: model names and behavior thresholds in one place. All six nodes will pull from this at construction time; none will hardcode model names. Defaults are `gpt-5.4` across the board for judgment-heavy nodes, `text-embedding-3-small` for embeddings, k=3 for retrieval, 0.4 for the review confidence threshold.

`GraphState` TypedDict: the shared state dict that flows through all nodes. TypedDict (not Pydantic) because LangGraph uses `Annotated` reducers for merge control — Pydantic doesn't compose with that pattern. Fields typed as `list[Any]` for now; subsequent issues will narrow them to specific Pydantic types as those are defined. All fields named and commented so the schema is readable as documentation.

Six stub nodes: `ingest`, `retrieve_context`, `extract_candidates`, `classify_themes`, `human_review`, `write_back`. Each accepts `GraphState`, returns `{}`. Sequential topology matches the architecture spec. Stubs confirmed to compile and pass state through without error.

`build_graph(config)`: constructs and compiles the graph. Takes an optional `GraphConfig`; defaults to production settings.

`.env.example` written — covers all current and new env vars including the three LangSmith vars (`LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`).

13 new tests in `test_graph.py`. All 51 tests (new + existing) pass.

**Key decisions:**

- **TypedDict for state, Pydantic for boundaries.** TypedDict is the LangGraph convention because reducers (`Annotated[list, operator.add]`) don't compose with Pydantic models. Pydantic is used for LLM output schemas and Sheets/Drive I/O boundaries — not graph state.

- **`InMemoryVectorStore`, not Chroma.** The vector store is rebuilt fresh from Sheets at the start of each run. Chroma is designed for persistent stores and is overkill; `InMemoryVectorStore` from `langchain-core` has no extra dependencies and is trivially swappable. Established in `GraphConfig` but the implementation comes in Issue #12.

- **Batch-in-state.** The graph processes the full manifest as a batch within a single invocation (`manifest_docs: list[dict]` in state). No per-document fan-out at this layer. LangGraph's `Send` API is available if we need parallelism later.

- **LangSmith tracing is automatic** once `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` are set. No instrumentation needed at the scaffold level — it will land on each real node as we build them.

**Deferred:**

- LangSmith GitHub Actions secrets — deferred to Issue #18 (CLI/Actions update).
- Actual trace verification (that a stub run produces a LangSmith entry) — requires live credentials; noted in the issue as a manual check, not a CI assertion.

**Open questions resolved:**

- Batch vs. per-document graph: batch-in-state. Simpler graph topology; `Send` available if needed later.

---

## Issue #10 — Ingest node: wrap extraction, parse individual follow-up questions

**Date:** 2026-03-24

**Branch:** `issue-10-ingest-node`

**What was built:**

`ingest.py` — the ingest node implementation and supporting types. No LLM calls; everything here is deterministic and runs without API credentials.

`IngestedDoc` and `SkippedDoc` TypedDicts — the first concrete state types. `GraphState` is narrowed from `list[Any]` to `list[IngestedDoc]` / `list[SkippedDoc]` for the ingest output fields.

`parse_questions(blob)` — the new behavior this issue adds. Parses the `follow_up_questions` text blob from `extraction.py` into a `list[str]` of individual question strings. Handles: numbered lists (`1.`, `1)`), bulleted lists (`-`, `*`, `•`), bare newlines, and markdown bold (`**Q?**`). Each non-empty line after stripping markers becomes one question. Single dense paragraph on one line → one question.

`run_ingest(manifest_docs)` — loops over raw manifest dicts, calls `extraction.extract()`, applies the gate check, parses questions, routes to `ingested_docs` or `skipped_docs`.

`ingest` node in `graph.py` updated from stub to real implementation.

`tests/fixtures/hard_case_note.txt` — representative fixture note with mixed formatting in the follow-up section: two numbered items, one bold question, one bulleted item.

25 new tests in `tests/test_ingest.py`. 76 total tests pass.

**Key decisions:**

- **Per-line = per question.** The simplest parse rule that handles real data. Multi-line questions are rare; splitting on sentence boundaries is fragile and not attempted. Revisit with LangSmith evidence after real runs.

- **Markdown bold stripped, not treated as a header.** `**Q?**` appears in real notes as emphasis, not a section marker. Stripping gives a clean question string.

- **`ingest.py` as its own module.** Question parser and `run_ingest` are independently testable without LangGraph. Establishes the pattern: each substantial node gets its own module (`extract_candidates.py`, `classify_themes.py`, etc.).

- **LangSmith trace:** LangGraph automatically traces the node. A `log.info` summary ("X docs — Y passed, Z skipped") appears in the trace logs alongside the `ingested_docs` / `skipped_docs` state diff.

**Deferred:**

- Multi-paragraph question parsing (rare in practice; revisit with real run evidence).

---

## Issue #11 — Theme Library: Pydantic schema and Google Sheets persistence

**Date:** 2026-03-25

**Branch:** `issue-11-theme-library`

**What was built:**

`theme_library.py` — `Topic` enum (20 national taxonomy topics), `QuestionType` enum (5 types), `ThemeRecord` Pydantic model, row serialization (`to_row` / `from_row`), tab utilities (`find_latest_theme_tab`, `theme_tab_name`), and Sheets API functions (`read_theme_library`, `write_theme_library`, `build_sheets_client`).

31 new tests in `test_theme_library.py`. 107 total tests pass.

**Key decisions:**

- **Tidy data model.** The classified notes tab is the fact table (one row per question per run); the theme library tab is the dimension table (one row per theme). They join on `sub_topic`. Source passages are NOT stored exhaustively in the theme library — that would bloat cells and violate the tidy model. The classified notes tabs are the canonical record of all source questions. This design enables non-technical editorial staff to use pivot tables directly in Google Sheets.

- **Representative passages: max 3, for display only.** `ThemeRecord.representative_passages` holds up to 3 example source questions for inline retrieval display (shown to reporters when reviewing candidates). `add_passage()` enforces the cap and deduplicates. Full passage history is in the classified notes tabs.

- **Occurrence count as denormalized integer.** Stored explicitly so the library tab is self-contained for scanning — editors shouldn't need to count classified notes rows to understand theme frequency.

- **Column-tolerant deserialization.** `from_row` uses header-name lookup, not positional indexing. Missing or extra columns use defaults rather than crashing. This means the schema can evolve across runs without breaking reads of older tabs.

- **`str, Enum` for Topic and QuestionType.** Serialize naturally to their string values (e.g., `"HOUSING"`, `"knowledge_gap"`), iterable for use in LLM prompts.

**The theme library tab is a two-way human interface.** Two distinct levels of correction:
- *Classified notes tab* — per-question decisions (Accept / Reject / Rename), handled by the Issue #16 feedback loop.
- *Theme library tab* — theme-level corrections. Editors can directly edit sub-topic labels, descriptions, topic assignments, and canonical forms between runs. `read_theme_library` reads the tab as-is, so any manual edits propagate automatically to the next run.

**Deferred:**

- Soft-rejection via a Status column in the theme library tab. Currently, editors reject a theme by deleting the row. That works for bootstrapping but leaves no record. A `Status` column with `active / rejected` would support a soft-delete audit trail — deferred until the bootstrapping phase is complete and the pattern is clear.

- `ARCHITECTURE.md` updated in the same session to document the tidy data model (fact/dimension design, pivot table implications, representative passages rationale).

---

## Issue #14 — classify_themes node: merge/split, question type, topic assignment

**Date:** 2026-03-25

**Branch:** `issue-14-classify-themes-node`

**What was built:**

`classify_themes.py` — the classify_themes node implementation. Two LLM calls per candidate, three inferences total.

`_MergeSplitDecision` internal schema: `{decision, matched_theme, confidence, reasoning}`. Used with `classify_model` (gpt-5.4).

`_QuestionTypeAndTopic` internal schema: `{question_type, question_type_confidence, low_confidence, proposed_new_type, topic}`. Used with `question_type_model`. Combines question type and national topic in one call — both are more mechanical than merge/split and don't confuse the model when combined.

`ClassifiedTheme` Pydantic model: the full output type. Carries merge/split decision, confidence, reasoning, `needs_review` flag, question type (with low-confidence and proposed-new-type flags), and national topic. `question_type="uncertain"` is normalised to `None`.

`build_merge_split_prompt(candidate) → list[dict]` — pure function. Formats retrieved similar themes as numbered lines. System prompt instructs model to lean NEW when uncertain — easier for editors to merge later than to split.

`build_question_type_prompt(candidate) → list[dict]` — pure function. Shows the full 5-label taxonomy with definitions. Also shows all 20 national topic labels for the constrained lookup. Both `low_confidence` and `proposed_new_type` fields are explained in the system prompt so the model knows to use them rather than forcing a pick.

`classify_one(candidate, merge_llm, qt_llm, review_threshold) → ClassifiedTheme` — runs both inferences and assembles the result.

`run_classify_themes(candidates, merge_llm, qt_llm, review_threshold) → (list[ClassifiedTheme], list[ClassifiedTheme])` — classifies all candidates, returns the full list and the `needs_review` subset.

`GraphState.classified_themes` and `GraphState.needs_review` narrowed from `list[Any]` to `list[ClassifiedTheme]`.

39 new tests in `tests/test_classify_themes.py`. 200 total tests pass, no warnings.

**Key decisions:**

- **Two LLM calls, not three.** Merge/split gets its own call on `classify_model` — it's the hard judgment and should stay focused. Question type + topic are combined in a second call on `question_type_model` — both are more constrained, and topic assignment is "a constrained lookup, not open inference" per the architecture spec. Combining them doesn't degrade quality and halves the number of API calls.

- **"Lean NEW when uncertain."** The merge/split system prompt explicitly instructs the model to prefer NEW when confidence is low. The reasoning: incorrect merges corrupt the Theme Library in compounding ways (a bad merge in run 1 becomes a misleading retrieval result in run 2). Incorrect splits are surfaced to editors for easy correction. This asymmetry justifies the bias.

- **`question_type="uncertain"` normalised to `None`.** The model can return "uncertain" when no label fits. Rather than storing that string in `ClassifiedTheme.question_type` (which downstream code would need to handle as a special case), it's normalised to `None`. The `proposed_new_question_type` field carries the model's description if it proposed an alternative.

- **`needs_review` is `confidence < threshold`, exclusive lower bound.** Confidence exactly at threshold (e.g., 0.40 with a 0.40 threshold) is NOT flagged. This matches the intent: the threshold is a floor below which we're uncertain, not a ceiling above which we're confident.

- **Lazy LLM construction in graph node.** Same pattern as #12 and #13 — `ChatOpenAI` instantiated only when `candidates` is non-empty, so cold-start and test graph invocations don't require `OPENAI_API_KEY`.

**Deferred:**

- Question type retrieval context. Issue #14 documents the hypothesis: "no retrieval needed for question type; taxonomy is stable enough to classify from the question alone." LangSmith will confirm.
- Confidence threshold calibration. Starting at 0.4 per the issue; to be tuned after bootstrapping runs.

---

## Issue #13 — extract_candidates node: LLM theme extraction from questions

**Date:** 2026-03-25

**Branch:** `issue-13-extract-candidates-node`

**What was built:**

`extract_candidates.py` — the extract_candidates node implementation and supporting types. One LLM call per follow-up question using `gpt-5.4` with structured output.

`ThemeCandidate` Pydantic model: `{doc_id, source_question, sub_topic, description, retrieved_context}`. The LLM generates only `sub_topic` and `description` via a separate internal `_ExtractedTheme` schema; `doc_id`, `source_question`, and `retrieved_context` are attached from input data, not by the model.

`build_extraction_prompt(question, similar_themes) → list[dict]` — pure function, no LLM call. Retrieved similar themes are formatted as numbered human-readable lines, not raw JSON. Cold-start (no similar themes) produces a message telling the model this may be a new sub-topic.

`run_extract_candidates(retrieval_context, llm)` — accepts the LLM as a parameter (injectable) so tests pass `FakeLLM` without credentials.

`GraphState.candidates` narrowed from `list[Any]` to `list[ThemeCandidate]`.

The `extract_candidates` node in `graph.py` is now a closure that captures `extract_model` from `GraphConfig`. `ChatOpenAI` is instantiated lazily — only when `retrieval_context` is non-empty — so cold-start graph runs don't require `OPENAI_API_KEY`.

29 new tests in `tests/test_extract_candidates.py`. 161 total tests pass, no warnings.

**Key decisions:**

- **One-to-one per the issue recommendation.** One `QuestionContext` → one `ThemeCandidate`. The hard-case test (`test_hard_case_ambiguous_question_produces_single_candidate`) verifies this contract holds for questions spanning two topics — the model is instructed to pick the most specific and actionable one.

- **`retrieved_context: list[dict]` in ThemeCandidate.** The similar themes provided as context are stored verbatim on the candidate so downstream nodes (`classify_themes`, `write_back`) know what evidence the model had. Typed as `list[dict]` rather than `list[SimilarTheme]` to avoid Pydantic/TypedDict interop friction.

- **Prompt separates system role (what a sub-topic IS) from user role (the specific question + context).** System prompt includes concrete examples of specific vs. generic labels so the model understands the level of specificity required. This structure also makes prompt ablation easy — swap the system prompt to test different framing without touching the user template.

- **Graph integration tests updated.** `test_ingest_node_populates_state` and `test_ingest_node_questions_in_state` in `test_ingest.py` were running the full graph and inadvertently triggering LLM calls once `extract_candidates` became real. Fixed by: (a) giving the graph integration test a `NO_QUESTIONS_DOC` fixture (no follow-up questions → empty retrieval_context → LLM never called), (b) changing `test_ingest_node_questions_in_state` to call `run_ingest` directly since question parsing is ingest logic, not graph topology.

**Deferred:**

- Narrative notes as additional context in the extraction prompt. Architecture spec describes narrative notes as "useful context but not the primary signal." Currently the prompt only sees the follow-up question + retrieved similar themes. Whether narrative notes improve sub-topic quality is an open empirical question for LangSmith evaluation after the first real run.
- One-to-many (one question → multiple candidates). The one-to-one rule is a starting constraint. If LangSmith shows genuine multi-theme questions are systematically collapsing into one muddled candidate, revisit before bootstrapping is complete.

---

## Issue #12 — retrieve_context node: in-memory vector store and semantic retrieval

**Date:** 2026-03-25

**Branch:** `issue-12-retrieve-context-node`

**What was built:**

`retrieve_context.py` — the retrieve_context node implementation and supporting types. No LLM calls; retrieval is deterministic given the embeddings.

`SimilarTheme` and `QuestionContext` TypedDicts — the output types for this node. `GraphState.retrieval_context` narrowed from `list[Any]` to `list[QuestionContext]`.

`build_vector_store(themes, embeddings)` — embeds each `ThemeRecord` as `"{sub_topic}: {description}"` into an `InMemoryVectorStore`. Returns `None` on cold start (empty library) without calling the embeddings object.

`retrieve_for_question(question, store, k)` — retrieves top-k similar themes for a single question. Returns `[]` if store is `None`. Handles k > number of themes gracefully.

`run_retrieve_context(ingested_docs, theme_library, embeddings, k)` — builds the store and produces one `QuestionContext` per follow-up question across all ingested docs.

The `retrieve_context` node in `graph.py` is now a closure (built inside `build_graph`) that captures `embedding_model` and `retrieval_k` from `GraphConfig`. `OpenAIEmbeddings` is instantiated lazily — only when the theme library is non-empty — so cold-start runs and existing graph tests don't require `OPENAI_API_KEY`.

`numpy>=1.24` added to project dependencies. `InMemoryVectorStore` uses cosine similarity via numpy; it is a transitive dependency that was missing from the explicit dependency list.

23 new tests in `tests/test_retrieve_context.py`. 132 total tests pass.

**Key decisions:**

- **Lazy embeddings in the graph node.** `OpenAIEmbeddings` requires `OPENAI_API_KEY` at construction time. Creating it eagerly in `build_graph` would break all tests that build the graph without credentials. The closure checks `theme_library` first; cold-start and test runs never touch the OpenAI client.

- **`embeddings` param is injectable.** `run_retrieve_context` accepts an `Embeddings` object (or `None` for cold start), not a model name string. This lets tests inject `FakeEmbeddings` without patching. The graph node is the one place that creates the real `OpenAIEmbeddings`.

- **Per-question retrieval.** One `QuestionContext` per follow-up question, not per document. More precise; scale is fine at this cadence (quarterly batch). Matches the issue decision and downstream node contracts.

- **`venue_context: list[Any]` stubbed as always `[]`.** The venue context slot is typed in `QuestionContext` now so downstream nodes have a stable contract. No retrieval is performed until the Meeting/Venue Knowledge Base is in scope. This avoids a schema change when that work lands.

- **`numpy` explicit in dependencies.** `InMemoryVectorStore` needs numpy for cosine similarity but langchain-core doesn't declare it as a hard dependency (it's behind a try/except `ImportError`). Making it explicit avoids a confusing runtime failure in any environment where numpy isn't coincidentally installed.

**Deferred:**

- Venue/institutional context retrieval — the slot is present in `QuestionContext` and the node, but always returns `[]`. Activating it requires the Meeting/Venue Knowledge Base, which needs human curation to bootstrap (see architecture spec).
- Async retrieval — `InMemoryVectorStore` supports async; switching to `asimilarity_search_with_score` would allow parallel per-question queries. Not worth the complexity at current scale; revisit if per-run latency becomes a concern.

---