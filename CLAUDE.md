# CLAUDE.md

This file is read automatically at the start of every Claude Code session. It is the working contract for this project. See `AGENTS.md` for repo conventions and code style. Do not modify either file without explicit instruction.

## Orient before acting

At the start of every session:

1. Read `AGENTS.md` — repo conventions, current code structure, how to run things.
2. Read `ARCHITECTURE.md` — the full system design (target state, not current state).
3. Read `HISTORY.md` — decisions made, work completed, things deferred.
4. Read the existing code — understand what is already built before proposing anything. The architecture doc describes where we're going; the code describes where we are.
5. Read the current issue (the human will provide it).
6. Confirm your understanding before writing any code.

If anything in the history, architecture, or existing code is ambiguous or contradicts the current issue, say so before proceeding.

## How we work

### Issues are the unit of work

Work happens one GitHub issue at a time. Do not start the next issue until the current one is complete and a history entry has been written. Do not propose doing multiple issues in one session unless asked.

Before any code is written in a new project phase, propose a set of GitHub issues covering the full scope. Each issue should be small enough to review in one sitting, focused on one thing, and written with a title, scope description, explicit acceptance criteria, and any open questions. Do not start coding until the issue list has been reviewed and approved.

### One branch per issue

Create a branch named `issue-{number}-{short-slug}` before writing any code. All work for the issue lives on that branch. Do not commit directly to `main`. The human reviews and merges.

### History is mandatory

After completing each issue, append an entry to `HISTORY.md` describing what was built, key decisions and why, anything deferred and why, and any open questions that emerged. This is not a summary of the diff — it should be readable by someone who wasn't in the session.

### The human is in the loop

The human reviews every issue before it's opened and every PR before it's merged. Do not make architectural decisions unilaterally — surface them as open questions in the issue or history entry.

## Tests

Write tests alongside the code, not after. Existing tests are the regression harness for the migration — keep them green.

**Unit tests** on classification logic, prompt construction, and any non-trivial data transformation.

**Integration tests** run the full graph against fixture notes checked into the repo. Fixtures should be real or representative notes, small enough for fast runs, deterministic.

**Hard-case tests are first-class.** Write explicit tests for:
- A question plausibly belonging to two sub-topics.
- A question that doesn't fit any question type cleanly.
- A note with inconsistent formatting the ingest node has to impute.
- A run where the theme library is empty (bootstrapping).

Tests against real APIs are deferred until after the first real run. Mark stubs clearly with `# TK: integration`.

## LangGraph and LangSmith specifics

Every LangGraph node is a named, traced unit. LangSmith traces should be readable by a non-engineer — log inputs and outputs with human-friendly labels, not raw dicts.

Each node's model is independently configurable. No hardcoded model names inside node logic. Configuration lives in one place.

## Documentation

Three audiences, three deliverables:

**The client (non-technical).** A system diagram. A plain-language explanation of what the system does and what to expect from each run. A guide to the Google Sheet: how to read it, how to approve/reject/rename a classification, what happens on the next run.

**The operator.** How to set up credentials. How to trigger a run. How to re-run over a date range. How to promote the theme library from bootstrapping to stable. What to do when something breaks.

**The developer.** `ARCHITECTURE.md` is the primary reference. Module and class docstrings explain why the module exists and what it owns, not just what it does.