---
marp: true
theme: default
paginate: true
style: |
  section {
    font-size: 1.4rem;
    padding: 2rem 3rem;
  }
  h1 { font-size: 2rem; margin-bottom: 0.5rem; }
  h2 { font-size: 1.6rem; color: #333; }
  table { font-size: 1.1rem; }
  code { background: #f0f0f0; padding: 0.1rem 0.4rem; border-radius: 3px; }
  .small { font-size: 1.1rem; }
---

# Documenter Themes
## What it does, how to use it

Signal Cleveland · Editorial Guide

---

## What problem does this solve?

Documenters file hundreds of meeting notes each year.

Each note ends with **follow-up questions** — things reporters didn't understand, wanted to pursue, or noticed weren't being followed up on.

**The problem:** These questions contain real community signal. But scattered across hundreds of notes, the patterns are invisible.

**The solution:** A system that reads the questions, identifies recurring civic themes, and surfaces them in a Google Sheet for editorial review.

---

## What the system reads

From each set of meeting notes, the system focuses on the **follow-up questions section**.

> *"How are lead service line replacements being prioritized by neighborhood?"*
> *"Who decides when a school is put on the closure list?"*
> *"Why hasn't the city responded to the noise complaints filed six months ago?"*

These questions — individually weak signals — become a map of community concern in aggregate.

Narrative notes and the single signal are also read as supporting context, but follow-up questions are the primary input.

---

## What the system produces

After each run, two new tabs appear in your Google Sheet:

| Tab | What it is |
|-----|-----------|
| `classified-notes-YYYY-MM-DD` | One row per follow-up question. **This is where you work.** |
| `theme-overview-YYYY-MM-DD` | A read-only summary of all confirmed themes. Use it to browse the library. |

The classified notes tab is the only place where editorial decisions are made.

---

## The Theme Library

The system tracks recurring civic issues in a **Theme Library** — a growing catalog of sub-topics that have appeared across Documenter notes.

Examples of sub-topics:
- *lead pipe replacement funding*
- *magnet school enrollment caps*
- *transit service cuts on high-ridership routes*
- *transparency in budget reporting*

When it processes a new question, the system checks the library first: **Is this something we're already tracking?** Over time, the library gets better at recognizing recurring themes.

**The library starts empty.** It grows through your decisions. Early runs will surface more new themes; later runs will connect more questions to existing ones.

---

## How to read a classified notes row

Each row is one follow-up question from one meeting. The system fills in its best guess; you confirm, correct, or reject.

| Column | Meaning |
|--------|---------|
| **Meeting date / body** | When and where |
| **Source question** | Exactly what the reporter wrote |
| **Sub-topic** | The civic issue — the system's core classification |
| **Sub-topic confidence** | How sure the system is (0–1). Below 0.7 → flagged for review. |
| **Needs review** | "yes" means the system wants your input |
| **Retrieved similar themes** | Existing library themes most similar to this question |

**Start here:** Filter **Needs review = yes** to see priority rows first.

---

## Retrieved similar themes

This column is the most important one for borderline calls.

It shows up to three existing library themes that are semantically closest to the question being reviewed. For each, you see:

> `2. transit service cuts on high-ridership routes — Frequency reductions on major routes (TRANSPORTATION)`

**Why it matters:** Before creating a new theme or choosing a new name, check what's already in the library. If a retrieved theme is a good match, use its exact label as the corrected sub-topic — that merges them rather than creating a near-duplicate.

---

## Filling in a Decision row

The **Decision** column accepts three values: `Accept`, `Reject`, or `Rename`.

| Decision | When to use it | What to also fill in |
|----------|---------------|----------------------|
| **Accept** | The proposed sub-topic is correct | Nothing else required |
| **Reject** | The question isn't a trackable theme, or the classification is too far off | Nothing else required |
| **Rename** | Close, but the label needs work — or it belongs under an existing theme | **Corrected sub-topic**: type the label you want |

**Rename to merge:** If a retrieved similar theme is a close match, type its exact label in Corrected sub-topic. That merges this question into the existing theme instead of creating a new one.

A well-reviewed row takes under a minute.

---

## Question types

Every classified question also gets a **question type** — what kind of knowledge gap or concern it expresses.

| Type | Meaning |
|------|---------|
| Knowledge gap | Doesn't understand how a process works |
| Process confusion | Doesn't understand who decides or how |
| Skepticism | A critique framed as a question, rooted in lived experience |
| Accountability | Something promised hasn't happened |
| Continuity | A thread that hasn't been picked up again |

If the type is wrong, use the **Question type override** dropdown. If none fit, use **Proposed new question type**.

These types are most useful for rollup analysis: of all housing themes, what proportion are accountability questions? That's where coverage planning value emerges.

---

## The feedback loop

Your decisions feed the next run.

```
Meeting notes → Agent → Classified notes tab → Your decisions
      ↑                                                  ↓
      └──────────── Theme Library (updated) ←────────────┘
```

At the **start of each new run**, the system:
1. Reads your Accept / Rename / Reject decisions
2. Updates the Theme Library accordingly
3. Processes new notes with the improved library

**You don't have to finish reviewing before the next run starts.** Whatever decisions are in the sheet get applied. Unreviewed rows stay available.

---

## When to trigger a run

Runs are triggered manually — nothing happens automatically.

**Trigger a run when:**
- Preparing for a quarterly coverage planning cycle
- After completing a review pass (to apply your decisions and get fresh classifications)
- After a significant batch of new meetings has been filed

**How:** GitHub Actions → the project repository → **Run workflow** button.

The run takes roughly 30–60 minutes. When it finishes, two new tabs appear in the Sheet. If it fails, the operator investigates — no partial results are written.

**Minimum cadence:** Quarterly. Monthly is better once the Theme Library is stable.

---

## Quick reference

| Task | How |
|------|-----|
| Find priority rows | Filter **Needs review = yes** |
| Accept | Decision = `Accept` |
| Reject | Decision = `Reject` |
| Rename / merge | Decision = `Rename` + label in Corrected sub-topic |
| Fix question type | Question type override dropdown |
| Browse all themes | Read the theme-overview tab |
| Trigger a run | GitHub Actions → Run workflow |

Full guide: `docs/client-guide.md`
