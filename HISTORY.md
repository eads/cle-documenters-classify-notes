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