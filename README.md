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
- LangChain for orchestration

## Working Principles

- Keep everything runnable locally first.
- Keep commits small and auditable.
- Prefer deterministic baselines before adding heavy LLM behavior.
- Never commit credentials or client-sensitive files.

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
