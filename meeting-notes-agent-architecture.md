# Meeting Notes Reporting Themes Agent — Architecture

## Overview

An agentic system that analyzes Documenters' notes from public meetings to extract, classify, and track themes across meetings over time. Replaces a static theme checklist with a dynamic, learning system grounded in two RAG corpora.

## Overall goals

We wish to use follow-up questions from the meetings to inform future coverage. 

For example, if Documenters are repeatedly asking questions about something related to housing (e.g. section 8 vouchers or tax credits for new construction), we want to ask: What are we missing here? What's confusing or interesting to the public? Do we need an explainer of the topic? Do we need to report further?  

We also want to analyze the corpus of follow-up questions at a high level to be able to ask things like: What are most common questions about a topic like housing?

Typical follow up questions fall into different broad categories, though this is by no means all of them or the only way to frame them: I don’t understand a process; don’t understand how a decision is made, opinion-disguised-as-question (skepticism); this has been mentioned before; there’s no follow up from something mentioned before.


## Input Structure

Each meeting note record contains:

- **Summary** — brief overview of the meeting (secondary analysis target)
- **Narrative notes** — extensive reporter observations (secondary analysis target)
- **Follow-up questions** — what the reporter flagged as unresolved or worth pursuing (primary analysis target)
- **Single signal** — distillation of the above -- _one_ topic to look into further of great community interest (lower signal, treat as a re-inforcing part of the follow-up questions)

## RAG Corpora

### 1. Theme Library

A vector store of themes extracted and confirmed from past meetings. Each theme record contains:
- Theme name and description
- Example quotes/passages that triggered it
- Meetings where it appeared (with dates and venue)
- Reporter-confirmed canonical form (after human review)

**Purpose:** The agent retrieves semantically similar past themes before proposing new ones, so it can decide: is this a new theme or a variant of something we already track?

### 2. Meeting/Venue Knowledge Base

Institutional memory about specific meetings, venues, and recurring actors. Records include:
- Meeting type and typical agenda structure
- Whether the meeting leans more ceremonial or substantive ("real debate happens at the subcommittee meeting the week before"), discursive or decision-oriented ("this is where the commision renders a final decision")
- Recurring attendees and their known affiliations/agendas
- Historical significance patterns ("major public transit news often comes out of this meeting")
- Locally relevant issues and publication-specific tendencies ("stadium funding is a popular topic with our audience") 

**Purpose:** Frames and weights theme extraction. A heated exchange at a ceremonial meeting lands differently than the same exchange at a decision-making body.

## Agent Graph (LangGraph)

```
[ingest] → [retrieve_context] → [extract_candidates] → [classify_themes] → [human_review] → [write_back]
```

### Nodes

**ingest**
Parse the note record. We're primarily concerned with follow-up questions and weigh them heavily; treat the single takeaway as effectively an overlapping part of the follow-up questions. The primary notes and summary are useful context, but we're more concerned with understanding the interests and knowledge gaps of the Documenters attending the meetings.

**retrieve_context**
Parallel retrieval from both corpora:

- Theme library: "what themes in follow-up questions have appeared in similar meetings?"
- Venue knowledge: "what do we know about this meeting body and its attendees?"

Both results passed as context to downstream nodes.

**extract_candidates**
LLM extracts candidate themes from follow-up questions, informed by retrieved venue context and theme library. 

**classify_themes**
For each candidate, the agent reasons:
- Is this a variant of an existing theme (merge) or genuinely new (add)?
- How confident? If borderline, route to human review.

This is the core agentic reasoning step — not a pipeline, requires judgment under uncertainty.

**human_review**
Low-confidence classifications surface to a reporter/editor queue. Reviewer confirms, rejects, or corrects. Confirmed themes write back to the theme library with the source passage as an example.

**write_back**
- Update theme library with new/confirmed themes
- Update meeting/venue knowledge base if new institutional patterns emerged
- Tag the source record with extracted themes

## LangSmith Integration

Trace every classification decision:
- Which themes were retrieved from the library
- Which venue context was applied
- Why the agent chose to merge vs. create new
- Human review outcomes over time

This gives you an audit trail and lets us evaluate whether retrieval is actually helping — key for iterating on embedding strategy.

## Key Design Challenges Worth Highlighting

**Merge vs. split decision** — the hardest problem here -- are "Housing affordability" and "displacement pressure" the same theme or different? The agent needs retrieved examples plus venue context to make a defensible call.

**Re-inforcing context** — can the narrative notes deepen our understanding of the follow-up questions? How should they be weighted as signal?  

**Staleness** — venue knowledge decays. A new mayor changes what a city council meeting means. The write-back loop needs a mechanism to flag stale institutional knowledge for re-review.

## Constraints / scale

We have $50,000 of OpenAI credits. Earlier versions of this rig cost a few dollars to process a quarter's worth of data (about 45 meetings after de-duplication). A full run on all documents (from 2020 through Q1, 2026) might run $80-$100. 

The group we're working with intends to run the system quarterly going forward.

Given the size of the corpus of notes and generous budget relative to the problem, we should NOT pre-maturely optimize but at the same should architect with an eye to replacing expensive frontier models with less-expensive models when performance is adequate.

That's because we intend to scale up immediately to the three other Documenters programs in Ohio (who all use the same note-taking template) and could scale up to many more nationally.