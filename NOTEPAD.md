  What was built

  gdrive.py — GoogleDocsClient:
  - from_env() — reads GOOGLE_APPLICATION_CREDENTIALS (standard Google convention)
  - list_folder_docs(folder_id) — paginates Drive API for all .document files in the folder
  - fetch_doc_text(gdoc_id) — fetches via Docs API with PREVIEW_SUGGESTIONS_ACCEPTED, so you always get the stakeholder-edited version
  - fetch_folder(folder_id) — does both, returns (successes, failures) so one bad doc doesn't kill the run

  text_extract.py — converts the Docs API JSON blob to markdown:
  - Headings → #/##/etc.
  - Bullet items → -
  - Tables → markdown tables (which your quality gate already detects)

  fetch CLI command:
  documenters-cle-langchain fetch \
    --folder 1abc...xyz \
    --out march_2026.json \
    [--credentials /path/to/key.json]
  Writes a manifest JSON you can immediately pass to classify.

  ---
  Service account setup

  1. https://console.cloud.google.com → APIs & Services → Enable Google Drive API and Google Docs API
  2. IAM & Admin → Service Accounts → Create service account (no special roles needed)
  3. Create a JSON key → download it
  4. Share the Drive folder with the service account's email address (looks like name@project.iam.gserviceaccount.com) — Viewer is enough
  5. export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json

  The duplicate-doc problem we discussed is still unresolved at the manifest level — once you run fetch and see what the names look like, we'll have enough signal to
  add deduplication.

  ---

