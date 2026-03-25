# HISTORY.md

Append-only log of work completed, decisions made, and things deferred. One entry per issue. Do not edit past entries.

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