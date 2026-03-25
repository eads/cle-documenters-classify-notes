# Meeting Notes Reporting Themes Agent — Architecture

## TL;DR

Signal Cleveland runs a network of community reporters — Documenters — who attend public meetings and file structured notes. Those notes include follow-up questions: things the reporter didn't understand, wanted to investigate further, or noticed weren't being followed up on. Individually, each question is a weak signal. In aggregate across hundreds of meetings over years, they're a map of what communities are confused about, skeptical of, and not getting answers on.

This system reads those notes from Google Drive, extracts and classifies the follow-up questions by sub-topic and question type, tracks recurring themes over time in a RAG-backed library, and surfaces low-confidence classifications to editors via Google Sheets for human review. It runs as a batch job triggered manually via GitHub Actions — no always-on infrastructure, no streaming, no complicated ops.

The approach came out of an iterative process: a working prototype was built first to test assumptions, taken to the client to pressure-test the problem framing, and the resulting architecture reflects what was learned in that exchange — including what to simplify, what the genuinely hard problems are, and what the editorial team can realistically maintain.

---

## Overall Goals

We wish to use follow-up questions from meetings to inform future coverage.

For example, if Documenters are repeatedly asking specific thematic questions about housing (e.g. Section 8 vouchers or tax credits for new construction), we want to ask: What are we missing here? What's confusing or interesting to the public? Do we need an explainer? Do we need to report further?

We also want to analyze the corpus of follow-up questions at a high level: What are the most common questions about a topic like housing, and what do those questions reveal about community needs?

Typical follow-up questions fall into a few broad question types, though this list is not exhaustive: I don't understand a process; I don't understand how a decision is made; opinion-disguised-as-question (skepticism, often rooted in lived experience); this has been mentioned before; there's been no follow-up on something mentioned before.

### Two-level classification

Every extracted theme is classified along two dimensions.

**Sub-topic** — the specific subject the question is about ("magnet school enrollment caps", "Browns stadium financing", "Section 8 voucher waitlists"). This is the primary unit of the Theme Library and the level at which recurring patterns are tracked over time. Sub-topics are assigned to a **topic** from a fixed national taxonomy (see below) for high-level aggregation. The topic assignment is a constrained selection, not an open inference — the list is known in advance and does not require RAG retrieval.

**Question type** — the epistemic posture of the question: what kind of gap or concern does it express? A working taxonomy, subject to revision during bootstrapping:

- *Knowledge gap* — the reporter doesn't understand how a process or program works.
- *Process confusion* — the reporter doesn't understand how a decision is made or who has authority.
- *Skepticism / opinion-as-question* — a challenge or critique framed as a question, often grounded in lived community experience.
- *Accountability* — something was promised or required and hasn't happened; asking for follow-through.
- *Continuity* — a prior thread that hasn't been picked up again.

These two dimensions are independent inferences. Sub-topic classification is the hard problem (see Key Design Challenges). Question type requires real judgment — the categories can blur in practice — but it does not require RAG retrieval and is not expected to need human review in normal operation.

The editorial value is in the intersection. Rolling up across meetings, you can ask: of all themes in the "housing" topic, what proportion are knowledge gaps vs. accountability questions? Of all "schools" themes, does skepticism dominate? These aggregations are where the system earns its keep for coverage planning — not by ranking individual questions, but by revealing the shape of community concern across a topic over time.

### Topic taxonomy

Topics are drawn from the Documenters national taxonomy and are used as the top-level rollup for sub-topics:

AGRICULTURE, ARTS, BUDGET, CENSUS 2020, CRIMINAL JUSTICE, DEVELOPMENT, EDUCATION, ELECTIONS, ENVIRONMENT, FINANCE, HEALTH, HOUSING, LABOR, LIBRARIES, PARKS, POLITICS, PUBLIC SAFETY, TRANSPORTATION, URBAN ANIMALS, UTILITIES.

---

## Execution Model

The system runs as a **manually-triggered GitHub Actions workflow**. There is no always-on infrastructure. An editor or reporter triggers a run when they want a fresh analysis pass. Signal Cleveland currently expects this to be quarterly, or before a planning cycle.

This shapes the architecture in important ways:

- All processing is **batch**, not streaming or real-time.
- Human review is **async**: the agent surfaces items to a Google Sheet and waits for the next run to incorporate feedback, rather than blocking on a live queue.
- Compute requirements are modest: a standard GH Actions runner with a six-hour budget is sufficient for the full corpus at current scale, because most computation happens via platform APIs.
- The OpenAI grant covers API costs generously; a full historical run (2020–Q1 2026) is estimated at $80–100 and a quarterly incremental pass costs a few dollars.

---

## Tech Stack

The system is written in **Python**. Inputs are **Google Docs** (meeting notes, read directly from Drive). Outputs are **Google Sheets** (human review queue and analysis results). Airtable is a plausible future replacement for Google Sheets if the team's needs outgrow it, and the output interface should be designed with that swap in mind.

The agent layer is built on **LangChain** (chain construction, prompt management, retrieval primitives), **LangGraph** (the agentic graph — nodes, edges, conditional routing, and state management), and **LangSmith** (tracing, evaluation, and human review audit trail).

How they fit together: LangChain handles the LLM calls and retrieval queries inside each node. LangGraph defines the graph topology — which nodes run, in what order, and how state passes between them. LangSmith wraps every run, recording which themes were retrieved and why the agent chose to merge vs. create a new theme. This trace is the primary tool for evaluating whether retrieval is actually helping and for iterating on embedding strategy.

---

## Input Structure

Notes are stored as Google Docs in a structured Drive folder hierarchy. The agent reads them directly from Drive. Because note-takers use inconsistent formatting (H2 vs. H3 vs. bolded lines for section headers), the ingest node imputes structure from labels rather than relying on fixed selectors.

Each note record contains:

- **Summary** — brief overview of the meeting (secondary or tertiary analysis target).
- **Narrative notes** — extensive reporter observations (secondary analysis target).
- **Follow-up questions** — what the reporter flagged as unresolved or worth pursuing (primary analysis target).
- **Single signal** — one topic of great community interest; treated as reinforcing context for the follow-up questions, not an independent signal.

---

## RAG Corpus: Theme Library

A vector store of themes extracted and confirmed from past meetings. Each theme record contains:

- Sub-topic name and description.
- Topic (assigned from the national taxonomy above).
- Question type classification.
- Example quotes and passages that triggered it.
- Meetings where it appeared (with dates and venue).
- Reporter-confirmed canonical form (after human review).

**Purpose:** The agent retrieves semantically similar past themes before proposing new ones, so it can decide: is this a new sub-topic or a variant of something we already track? Question type is re-inferred fresh on each pass and is not used for retrieval — it is applied after the sub-topic merge/split decision is made.

**Cold start and bootstrapping:** The Theme Library begins empty. The bootstrapping plan is to run the agent against a seed corpus (likely 2025 + Q1 2026), conduct a human review pass, run again, and review again before considering the system production-ready. Subsequent runs retrieve against an increasingly populated library, reducing the proportion of new candidates and improving merge/split decisions over time. Ongoing adjustment after launch is expected.

### Persistence and the Google Sheets interface

Due to service account and workspace restrictions, the agent reads and writes through a single pre-existing Google Sheet using named tabs. Each run produces or updates two tabs:

**Classified notes tab** — one row per follow-up question processed in this run, with sub-topic, topic, question type, confidence, and source metadata. Low-confidence sub-topic classifications are flagged here for human review. The agent writes; reporters read and fill in the decision columns:

- Meeting date, body, and source question verbatim (agent, read-only).
- Proposed sub-topic label (agent, read-only).
- Proposed topic from national taxonomy (agent, read-only).
- 2–3 retrieved similar themes from the library — the evidence behind the proposal (agent, read-only).
- Confidence level (agent, read-only).
- Question type assignment (agent, read-only).
- Proposed new question type, if the model flagged low confidence (agent, read-only).
- **Decision** — Accept / Reject / Rename (reporter, dropdown).
- **Corrected sub-topic label** — free text, only needed for Rename; to merge into an existing theme, the reporter types that theme's canonical name (reporter).
- **Question type override** — dropdown, only if the assignment is wrong (reporter).
- **Proposed new question type** — free text, only if no existing label fits (reporter).
- **Notes** — optional (reporter).

The retrieved similar themes column is the most important design element. It gives the reporter the context to decide whether a borderline candidate should stand alone or fold into something that already exists. Without it, Rename is a guess.

**Theme library tab** — a human-readable and human-editable view of the full Theme Library: all confirmed sub-topics, their topic assignments, question type distributions, source meeting count, and canonical descriptions. Reporters and editors can make direct corrections here between runs. The next run reads this tab as its source of truth before querying the vector store, so manual edits propagate automatically.

**Tidy data model — fact table and dimension table.** The two tabs form a simple relational structure:

- The **classified notes tab is the fact table**: one row per follow-up question per run, with the source question verbatim, sub-topic assignment, topic, question type, confidence, and meeting metadata. Every individual question that was processed lives here.
- The **theme library tab is the dimension table**: one row per confirmed sub-topic theme, with rollup counts (occurrences, question type distribution) and up to 3 representative source passages for retrieval display.

They join on `sub_topic`. To find all source questions for a theme, filter the classified notes by `sub_topic`. To find all themes that appeared in a given meeting, filter by URL or meeting date.

This structure is intentional and load-bearing. It means non-technical editorial staff can build pivot tables directly in Google Sheets — occurrences by topic, question type distributions over time, which meetings produced the most new themes. The fact table is the analysis surface; the theme library is the lookup. Source passages are **not** stored exhaustively in the theme library — the classified notes tabs are the canonical record. The theme library carries only a small number of representative passages (up to 3) for inline display when the agent shows retrieved similar themes to a reporter. All historical passage retrieval goes through the classified notes tabs.

**Theme library versioning (bootstrapping phase):** Each run writes a new theme library tab, named by run date. The next run seeds from the most recent tab — absorbing any renames, rejects, and human corrections made there — and writes a fresh tab with the updated library. Nothing is ever overwritten; full history is preserved across tabs with no merge labor required.

This is a pragmatic solution appropriate for the bootstrapping phase, not a permanent architecture. Once the library has stabilized and the team is confident in the classifications, the appropriate next step is to designate a canonical tab and move to an append-only model — or, if the system has earned real investment by that point, replace Google Sheets with a proper database. The two-tab-per-run approach is the right call now precisely because it keeps options open and failure cheap.

---

## Future Enhancement: Meeting/Venue Knowledge Base

A second RAG corpus — institutional memory about specific meeting bodies, their typical agenda structure, recurring attendees, and historical significance patterns — is a natural evolution of this system. It would allow the agent to weight theme extraction by context: a heated exchange at a ceremonial meeting lands differently than the same exchange at a decision-making body.

This corpus is not in scope for the initial build. Unlike the Theme Library, it cannot be bootstrapped from the notes themselves — the critical institutional knowledge has to come from human curation. It is named here so the architecture can accommodate it later without restructuring the graph (the `retrieve_context` node already has a parallel retrieval slot for it).

---

## Agent Graph (LangGraph)

```
[ingest] → [retrieve_context] → [extract_candidates] → [classify_themes] → [human_review] → [write_back]
```

### Nodes

**ingest**
Read the note document from Google Drive. Impute section structure (the agent infers which lines are headers and which are body text, accounting for inconsistent formatting across note-takers). Parse out follow-up questions, single signal, narrative notes, and summary. Weight follow-up questions heavily; treat the single signal as overlapping reinforcement rather than an independent input. Narrative notes and summary are useful context but not the primary signal — we care about the interests and knowledge gaps of the Documenters attending the meetings.

**retrieve_context**
Query the Theme Library for semantically similar sub-topics from past meetings. Results passed as context to downstream nodes. (A second retrieval slot for venue/institutional context is stubbed here for the future enhancement described above.)

**extract_candidates**
LLM extracts candidate themes from the follow-up questions, informed by Theme Library retrieval results. Each candidate includes a proposed sub-topic label and description, drawn from or compared against retrieved examples.

**classify_themes**
For each candidate, the agent makes two independent classifications:

1. **Sub-topic merge/split**: is this candidate a variant of an existing theme (merge) or genuinely new (add)? If borderline, route to human review. This is the core agentic reasoning step — it requires judgment under uncertainty and is where LangSmith tracing does its most important work.
2. **Question type**: assign one of the taxonomy labels above. The categories can blur in practice — skepticism shades into accountability, continuity into accountability — so the model is given definitions and examples for each type, but is also instructed to flag low confidence or propose a new type rather than forcing a pick. Those flags are the bootstrapping signal: if two types are consistently conflated, or a recurring posture doesn't fit any label, that's evidence the taxonomy needs adjustment before it hardens.

**Topic** is assigned by matching the sub-topic to the national taxonomy — a constrained lookup, not open inference.

**human_review**
Low-confidence sub-topic classifications are flagged in the classified notes tab of the Google Sheet (see RAG Corpus above). The design principle is that a reporter should be able to action a row in under a minute without reading documentation — the agent does the cognitive work up front, the human makes a judgment call. The next run reads the Decision column and routes accordingly: Accept and Rename write to the Theme Library, Reject discards.

**write_back**

- Update Theme Library with new and confirmed themes (sub-topic, topic, question type, source passage, meeting metadata).
- Tag the source record with extracted theme classifications.

---

## LangSmith Integration

Trace every classification decision:

- Which sub-topics were retrieved from the Theme Library.
- Why the agent chose to merge vs. create new.
- Question type assignments and any low-confidence flags.
- Human review outcomes over time.

This gives an audit trail and enables evaluation of whether retrieval is actually helping — essential for iterating on embedding strategy and for knowing when a cheaper model can replace a frontier one at a given node.

---

## Key Design Challenges

**Sub-topic merge vs. split** — the hard problem. Are "housing affordability" and "displacement pressure" the same sub-topic or different? Basic topical categorization turns out to be easy; the LLM handles it reliably without retrieval. The sub-topic boundary decision is where the interesting failure modes live — it requires retrieved examples plus judgment, and the bootstrapping runs are specifically designed to surface and resolve these calls before the system is considered production-ready.

**Reinforcing context** — can the narrative notes deepen our understanding of the follow-up questions? The current design treats them as secondary context passed to `extract_candidates`. How much they actually help is an open empirical question that LangSmith evaluation will clarify over time.

**Structure imputation** — because note-takers use inconsistent formatting, the ingest node does meaningful work before any LLM call. This is already functional and is the most operationally proven part of the system.

---

## Constraints and Scale

**Cadence:** Signal Cleveland has committed to quarterly runs at minimum. Monthly is probably the right rhythm once the Theme Library is stable — there are enough meetings per month to surface patterns, and a shorter cycle catches emerging themes faster. Weekly is likely too sparse until the system scales to additional Documenters programs. This is a judgment call for the editorial team once bootstrapping is complete.

**Model strategy:** Use frontier models from the start, and treat this as a deliberate architectural choice rather than a concession to laziness. The argument: a weaker model making systematic errors during bootstrapping corrupts the Theme Library in ways that compound. A bad sub-topic merge in run one becomes a retrieval result that misleads run two. It also burns human review time — every bad classification that surfaces to the sheet is a row a reporter has to read and correct. Token costs are trivial; editor time is not. You spend more per token during the seed runs, but you're buying data quality and human attention that are both genuinely hard to recover once squandered. Given the grant size and the small per-run cost, this is an easy call.

The current model choices: `gpt-5.4` as the frontier model for judgment-heavy nodes, `gpt-5-mini` as the lower-cost option for more mechanical steps. `gpt-5-mini` is only marginally more expensive than `gpt-4o-mini` and performs substantially better — going cheaper than `gpt-5-mini` is a false economy. Both choices are configurable per node and should be revisited with LangSmith evidence after the first real runs.

Once the Theme Library is populated, question type behavior is understood, and the bootstrapping review passes are complete, real LangSmith traces will show actual model behavior at each node. That is the right time to ask which nodes can drop to `gpt-5-mini` — with evidence, not intuition. The likely path: `extract_candidates` first (relatively mechanical extraction), `classify_themes` last (merge/split judgment is where quality matters most).

**Scaling path:** The immediate next step after the Cleveland pilot is three other Ohio Documenters programs using the same note-taking template. Longer term, the system could scale to many programs nationally. The architecture should not assume Cleveland-specific structure beyond what is already abstracted into the Theme Library.