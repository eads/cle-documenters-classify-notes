# Documenters Notes Agent

A LangGraph pipeline that reads Cleveland Documenter meeting notes from Google Drive, extracts follow-up questions, classifies them by recurring civic sub-topic and question type, and writes results to a Google Sheet for editorial review. Each run builds on prior reviewer decisions — the Theme Library grows over time and improves classification quality.

For the full system design, see `ARCHITECTURE.md`. For the editorial team's guide to the Google Sheet, see `docs/client-guide.md`. For repo conventions and current code structure, see `AGENTS.md`.

---

## How it works

```
fetch → pipeline (ingest → retrieve → extract → classify → write)
```

1. **fetch** — pull Google Docs from a Drive folder into a local manifest JSON
2. **ingest** — parse each doc: extract follow-up questions, summary, notes, single signal
3. **retrieve** — query the Theme Library for similar past sub-topics (cold start: empty)
4. **extract** — LLM identifies candidate sub-topics from the follow-up questions
5. **classify** — LLM decides merge vs. new for each candidate; assigns question type
6. **write** — appends two new tabs to the Google Sheet:
   - `classified-notes-YYYY-MM-DD` — one row per question, decision columns blank for editors
   - `theme-overview-YYYY-MM-DD` — materialized Theme Library cache for the next run

Editors fill in Accept / Reject / Rename decisions in the classified-notes tab. Those decisions are applied at the start of the next run to update the Theme Library.

---

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- OpenAI API key
- Google service account credentials with Sheets + Drive access
- An existing Google Sheet (the pipeline appends tabs; it does not create the spreadsheet)

---

## Setup

```bash
uv sync
```

Copy `.env.example` to `.env` and fill in:

```
OPENAI_API_KEY=sk-...
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
ROOT_DRIVE_FOLDER=<Drive folder ID>
CLASSIFIER_OUTPUT_SHEET=<Google Sheet ID>

# Optional
GOOGLE_IMPERSONATE_USER=user@example.com   # domain-wide delegation
LANGSMITH_TRACING=true                     # LangSmith tracing
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=cle-documenters
```

---

## Running

### Step 1 — Fetch docs from Drive

```bash
uv run documenters-cle-langchain fetch \
  --folder DRIVE_FOLDER_ID \
  --out data/manifest_2026.json \
  --year 2026
```

Fetches all docs from the folder, deduplicates, and writes a manifest JSON. Use `--month March` to narrow to a single month.

### Step 2 — Run the pipeline

```bash
uv run documenters-cle-langchain pipeline \
  --manifest data/manifest_2026.json \
  --out data/run_summary.json \
  --sheet-id YOUR_SHEET_ID
```

Reads the manifest, runs the full LangGraph pipeline, and writes two new tabs to the Sheet. `--sheet-id` defaults to the `CLASSIFIER_OUTPUT_SHEET` env var. `--run-date YYYY-MM-DD` overrides the tab date (defaults to today).

### Dedup only

```bash
uv run documenters-cle-langchain dedup \
  --input data/manifest_2026.json \
  --review data/dedup_review.md
```

Deduplicates a manifest in place and optionally writes a markdown review of dropped docs.

---

## Development

```bash
uv run pytest          # run all tests
uv run pytest -x -q    # fail fast, quiet
```

Key modules:

| File | Purpose |
|------|---------|
| `graph.py` | LangGraph graph definition and node wiring |
| `extract_candidates.py` | LLM extraction of candidate sub-topics |
| `classify_themes.py` | LLM merge/split decision and question type assignment |
| `theme_library.py` | ThemeRecord schema, Sheets persistence, vector store |
| `feedback.py` | Derives updated Theme Library from prior decisions |
| `write_back.py` | Classified notes tab construction and Sheets formatting |
| `ingest.py` | Document parsing and section extraction |
| `gdrive.py` | Google Drive / Docs API client |
