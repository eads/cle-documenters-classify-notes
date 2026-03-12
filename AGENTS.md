# AGENTS

Working conventions for humans and coding agents in this repository.

## What This Is

A local-first pipeline that classifies Cleveland public meeting notes from Google Drive into civic topic categories. No web server, no database — fetch, process, write files.

## Architecture

```
src/documenters_cle_langchain/
  cli.py          — argparse entrypoint (fetch / dedup / pipeline commands)
  pipeline.py     — orchestrates stages, defines PipelineDoc / PipelineResult
  classifiers.py  — two-pass LLM classifier (MeetingClassifier)
  extraction.py   — deterministic section parser (no LLM)
  gate.py         — required-field filter
  dedup.py        — checksum + name-containment deduplication
  manifest.py     — manifest JSON loading and ManifestDocument schema
  gdrive.py       — Google Drive / Docs API client
  schemas.py      — shared Pydantic boundary types
```

## Key Design Decisions

- **Deterministic extraction first.** The parser in `extraction.py` uses regex, no LLM. LLM only enters at the classification stage.
- **Two-pass classification.** Initial pass uses summary + follow-up questions + single signal with a fast/cheap model. If any category score lands in the ambiguous band (0.3–0.7), a second pass with full notes uses the stronger model.
- **Gate before LLM.** Docs missing required fields (agency, date, summary, notes) are logged and skipped before any LLM call.
- **Category config is a single list.** Add topics in `CATEGORIES` in `classifiers.py` — the prompt, schema, and CSV columns all derive from it.

## Running Locally

```bash
uv run documenters-cle-langchain pipeline \
  --manifest 2026.json \
  --out results_2026.json \
  --csv-out results_2026.csv
```

Requires `OPENAI_API_KEY` and Google credentials in `.env`.

## Repo Standards

- Python only. Dependency management via `uv`.
- No secrets, tokens, or client documents in commits.
- Keep `.env` local; provide `.env.example` for new vars.
- Outputs (JSON, CSV, manifests) are gitignored — keep them local.

## Commit Style

- Terse and clear. Prefixes: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`.
- One logical change per commit.
