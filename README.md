# documenters-cle-langchain

Python + LangChain pipeline that fetches Cleveland public meeting notes from Google Drive, extracts structured metadata, and classifies each meeting across civic topic categories.

## Requirements & Setup

**Prerequisites:**
- Python 3.12
- [`uv`](https://docs.astral.sh/uv/) (preferred environment manager)
- OpenAI API key
- Google service account credentials (for org-restricted Drive folders) or a Google API key (for public/shared folders)

**Tooling:**
- LangChain + `langchain-openai` for LLM orchestration
- Pydantic for structured output schemas
- `python-dotenv` for local config

**Install:**

```bash
uv sync
```

**Configure:**

Copy `.env.example` to `.env` and fill in credentials:

```
OPENAI_API_KEY=...
GOOGLE_API_KEY=...              # public/shared folders
GOOGLE_APPLICATION_CREDENTIALS=...  # path to service account JSON (org-restricted folders)
ROOT_DRIVE_FOLDER=...           # default folder ID for fetch
CLASSIFIER_OUTPUT_FOLDER=...    # Drive folder ID for classifier output sheets
```

## Pipeline

```
fetch → dedup → extract → gate → classify → JSON + CSV
```

1. **fetch** — pull all Google Docs from a Drive folder into a local manifest JSON
2. **dedup** — remove duplicates (checksum + name-containment; newest wins)
3. **extract** — deterministic parse of metadata and sections (agency, date, summary, follow-up questions, notes, single signal)
4. **gate** — drop docs missing any required field (agency, date, summary, notes)
5. **classify** — two-pass LLM topic classifier:
   - Initial pass: summary + follow-up questions + single signal → `gpt-5-mini`
   - If any category score is ambiguous (0.3–0.7): re-run with full notes → `gpt-5.4`

## Output

**JSON** — full structured results including all extracted fields, topic scores, and classification metadata.

**CSV** — one row per document: `web_url`, `name`, `date`, `agency`, `model_used`, and per-category columns for score, label (`certain` / `ambiguous` / `unlikely`), and identified topics.

## Usage

Run the full pipeline from fetch through classification:

Note that for the moment, fetch must be run separately from the processing steps.

```bash
# Fetch docs from a Drive folder
uv run documenters-cle-langchain fetch \
  --folder DRIVE_FOLDER_ID \
  --out data/docs_2026.json \
  --year 2026

# Run extract, gate, and classify on a manifest
uv run documenters-cle-langchain pipeline \
  --manifest data/docs_2026.json \
  --out data/results_2026.json \
  --csv-out data/results_2026.csv
```

**Subcommands** — run individual steps independently:

```bash
# Dedup a manifest and write a review file
uv run documenters-cle-langchain dedup \
  --input data/docs_2026.json \
  --review data/dedup_review.md
```

## Topic Categories

Categories are configured in `classifiers.py` — add a new `(slug, label, description)` tuple to `CATEGORIES` and it will appear in both the classifier and the CSV output with no other changes.

Current categories: **Civic Infrastructure**, **Schools & Education**.
