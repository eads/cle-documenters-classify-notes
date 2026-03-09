# documenters-cle-langchain

Local-first Python + LangChain project for a real workflow:

1. classify a large Google Drive document set into A/B buckets,
2. run a sub-agent pipeline on B documents,
3. save extraction outputs for downstream business use.

## Problem Statement

The client has many documents in Google Drive, grouped by date-coded folders.
Formatting is loosely standardized, but not reliably structured.

Current A/B split for v1:

- A: recent documents
- B: old documents that need deeper extraction

## Scope For The Tryout

Build a simple but real agent system that can:

1. crawl/list relevant docs from Drive,
2. classify each document into A or B,
3. trigger a B-only extraction sub-agent,
4. persist structured outputs (JSON/CSV) locally.

## Stepwise Build Plan

1. Docs and operating rules (this commit).
2. Python project scaffold with `uv`.
3. Environment/config loader with `.env`.
4. Drive ingestion (list files, fetch text).
5. A/B classifier chain.
6. B extraction sub-agent chain.
7. CLI entrypoint for local runs.
8. Basic evaluation set + metrics (precision/recall for A/B, extraction completeness).

## Proposed Architecture

- `ingest`: Google Drive file discovery + text loading.
- `classify`: A/B routing logic (rule-based first, LLM-assisted next).
- `extract`: sub-agent flow for B docs (field extraction + validation).
- `storage`: local artifacts, logs, and run manifests.
- `cli`: run commands for classify-only and classify+extract modes.

## Tooling

- Python 3.11+
- `uv` for dependencies and virtual environment management
- `python-dotenv` for local credentials and config loading
- `pydantic` for boundary validation (manifest rows and LLM structured outputs)
- LangChain for orchestration

## Working Principles

- Keep everything runnable locally first.
- Keep commits small and auditable.
- Prefer deterministic baselines before adding heavy LLM behavior.
- Never commit credentials or client-sensitive files.

## Open Questions for Client

These need answers before the pipeline can be fully automated. A deduplication review file (with Drive links) can be generated to help answer some of them.

### Deduplication

- **Which version of a meeting doc should be kept when duplicates exist?**
  Currently: newest by Google Drive modification time. Is that always right, or does an editor sometimes prefer an older version?

- **Are suggestions always authoritative?**
  Some docs have a stakeholder's suggestions tracked in Google Docs suggestion mode. The pipeline tries to accept all suggestions automatically. Are there cases where the original text should be preferred over a suggestion?

- **Should duplicates ever be merged rather than one discarded?**
  E.g. one version has better notes, another has a better single signal.

### Document Structure

- **Are all of these sections always expected?** Summary, Follow-Up Questions, Notes, Single Signal.
  What should happen when a section is missing entirely?

- **Is "Single Signal" always a single paragraph, or can it be a list?**

- **Are there other section names in use** beyond the ones above?
  (The template appears to vary across documenters and time.)

- **Who should be notified when a doc fails extraction** (missing fields, low confidence)?
  Current decision: log and skip. Failed docs are not written to the sheet.

### Output / Destination

- **Which Google Sheet should extraction results go to?**
  Who owns it? Should the pipeline append rows or overwrite?

- **What columns does the client actually need in the sheet?**
  Current assumption: meeting name, agency, date, documenter, summary, single signal, Drive URL.

## Immediate Next Step

Wire a deterministic metadata ingestion + recent/old classifier slice behind the CLI.

## Current Classify Scaffold

`classify` currently runs a deterministic parse-quality gate and stubs LLM escalation for low-quality documents.

Example:

```bash
uv run documenters-cle-langchain classify \
  --manifest data/examples/manifest.sample.json \
  --cutoff-days 365
```

Expected output includes:

- total docs
- parseable docs
- needs-review docs
- document ids that would be handed off to an LLM parse-repair stage
