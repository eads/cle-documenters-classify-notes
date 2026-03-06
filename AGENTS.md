# AGENTS

This file defines how humans and coding agents should work in this repository.

## Mission

Deliver a practical LangChain agent system that:

1. classifies Google Drive documents into A/B,
2. routes B documents into a sub-agent extraction workflow,
3. outputs clean structured data for business use.

## Repo Standards

- Language: Python only.
- Dependency management: `uv`.
- Environment variables: `.env` (loaded via `python-dotenv`).
- Runtime target: local development first.
- Logging: structured and concise; include document id/path references when possible.

## Implementation Priorities

1. Correctness and reproducibility.
2. Small, reviewable commits.
3. Clear interfaces between classify and extract steps.
4. Fast local feedback loops (CLI + tests).

## Commit Style

- Keep commit messages terse and clear.
- Use prefix hints when helpful: `docs:`, `chore:`, `feat:`, `fix:`.
- One logical change per commit.

## Safety Rules

- Do not commit secrets, tokens, or client docs.
- Keep `.env` local and provide `.env.example` as needed.
- Prefer redacted sample documents for tests and demos.

## Expected Workflow

1. Add or update a minimal plan in `README.md` when scope changes.
2. Implement the smallest vertical slice that runs end-to-end.
3. Add tests for routing and extraction behavior.
4. Keep outputs under a predictable local directory (`data/outputs/` once scaffolded).

## First Vertical Slice Target

- Ingest document metadata from Drive.
- Classify recent vs old.
- For old docs, extract one or two required fields.
- Save results to local JSON.
