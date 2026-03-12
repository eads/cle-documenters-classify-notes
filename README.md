# documenters-cle-langchain

Python + LangChain pipeline that fetches Cleveland public meeting notes from Google Drive, extracts structured metadata, and classifies each meeting across civic topic categories.

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

```bash
# Fetch docs from a Drive folder
uv run documenters-cle-langchain fetch \
  --folder DRIVE_FOLDER_ID \
  --out 2026.json \
  --year 2026

# Run the full pipeline
uv run documenters-cle-langchain pipeline \
  --manifest 2026.json \
  --out results_2026.json \
  --csv-out results_2026.csv

# Dedup a manifest and write a review file
uv run documenters-cle-langchain dedup \
  --input 2026.json \
  --review dedup_review.md
```

## Configuration

Credentials and API keys go in `.env` (see `.env.example`):

```
OPENAI_API_KEY=...
GOOGLE_API_KEY=...         # public/shared folders
GOOGLE_CREDENTIALS=...     # path to service account JSON (org-restricted folders)
ROOT_DRIVE_FOLDER=...      # default folder ID for fetch
```

## Topic Categories

Categories are configured in `classifiers.py` — add a new `(slug, label, description)` tuple to `CATEGORIES` and it will appear in both the classifier and the CSV output with no other changes.

Current categories: **Civic Infrastructure**, **Schools & Education**.

## Tooling

- Python 3.12, `uv`
- LangChain + `langchain-openai` for LLM orchestration
- Pydantic for structured output schemas
- `python-dotenv` for local config

## Open Questions for Client

### Deduplication

- Which version of a meeting doc should be kept when duplicates exist? Currently: newest by modification time.
- Are Google Docs suggestions always authoritative, or should original text ever be preferred?

### Document Structure

- Are Summary, Follow-Up Questions, Notes, and Single Signal always expected? What should happen when a section is missing?
- Are there other section names in use beyond these four?
- Who should be notified when a doc fails the extraction gate?

### Output / Destination

- Which Google Sheet should results go to? Append or overwrite?
- What columns does the client need beyond what's currently in the CSV?
