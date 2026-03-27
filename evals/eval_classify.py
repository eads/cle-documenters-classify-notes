"""eval_classify.py — LangSmith eval for the extract + classify pipeline.

Runs the classify_one pipeline against a small dataset of real follow-up
questions from fixture meeting notes with known expected outcomes.

Requires real API keys (OPENAI_API_KEY, LANGSMITH_API_KEY).  Not part of the
normal pytest suite — run manually:

    uv run python evals/eval_classify.py

Results appear in LangSmith under the project set by LANGSMITH_PROJECT
(default: cle-documenters).

Note: this eval exercises classify_one with raw LLMs, which is the interface
introduced in issue #60 (search_theme_library tool).  If running against main
before #60 is merged, the classify_one call signature will need a minor update
(pass structured-output LLMs directly instead of raw ones).
"""
from __future__ import annotations

import sys
import os

# ---------------------------------------------------------------------------
# Eval dataset
#
# Questions drawn from real fixture notes in tests/fixtures/.  Expected outputs
# are deliberately permissive (sets of acceptable values) to account for
# reasonable model variance.  The eval measures accuracy on two axes:
#   - topic_match:         predicted national topic in expected_topics
#   - question_type_match: predicted question type in expected_question_types
# ---------------------------------------------------------------------------

DATASET_NAME = "cle-documenters-classify-eval-v1"

EXAMPLES = [
    # --- Cuyahoga County Land Bank (tests/fixtures/fixture_land_bank.txt) ---
    {
        "question": "Does the land bank track what happens to housing and their residents once it's built?",
        "sub_topic": "land bank resident outcomes post-development",
        "description": "Whether the land bank follows up on housing quality and resident well-being after building projects are completed.",
        "expected_topics": ["HOUSING", "DEVELOPMENT"],
        "expected_question_types": ["knowledge_gap"],
    },
    {
        "question": "How was the dispute over who chaired the board resolved?",
        "sub_topic": "land bank board chair selection process",
        "description": "The process by which a conflict over the board chair position was handled, including potential conflicts of interest.",
        "expected_topics": ["DEVELOPMENT", "POLITICS"],
        "expected_question_types": ["process_confusion", "continuity"],
    },
    {
        "question": "What is going on with lawsuits against land banks? Chair Cromes wondered if there are other lawsuits against land banks like the one against him. Why was he sued and why would this be an issue for other land banks?",
        "sub_topic": "land bank legal liability and litigation",
        "description": "Pending lawsuits against land banks and whether legal exposure is a systemic issue across similar organizations.",
        "expected_topics": ["DEVELOPMENT"],
        "expected_question_types": ["knowledge_gap", "accountability"],
    },

    # --- Public Safety Technology Advisory Committee (tests/fixtures/fixture_public_safety.txt) ---
    {
        "question": "Although dates are being discussed as far as when all that is promised will be set in stone, I'm left wondering if these things are actually going to happen. Is there really a for-certain 'When' for oversight and transparency?",
        "sub_topic": "police technology oversight timeline",
        "description": "Whether concrete timelines exist for delivering promised oversight and transparency measures for police surveillance technology.",
        "expected_topics": ["PUBLIC SAFETY"],
        "expected_question_types": ["accountability", "skepticism"],
    },
    {
        "question": "Since Mayor Justin Bibb's 2022 pledge for more oversight and transparency regarding these technologies, certain meetings have been held about these issues. I'm curious as to why these issues are only being addressed in a public meeting with commissioners and important teams two years later.",
        "sub_topic": "delayed police surveillance oversight",
        "description": "The two-year lag between the mayor's 2022 pledge for police tech oversight and the first substantive public meetings on the topic.",
        "expected_topics": ["PUBLIC SAFETY"],
        "expected_question_types": ["accountability", "skepticism"],
    },
    {
        "question": "How can we encourage more accountability for officials?",
        "sub_topic": "civic mechanisms for official accountability",
        "description": "Community tools and processes for holding public officials accountable to their commitments.",
        "expected_topics": ["PUBLIC SAFETY", "POLITICS"],
        "expected_question_types": ["accountability", "process_confusion"],
    },

    # --- Cleveland City Council Health Committee (tests/fixtures/fixture_single_question.txt) ---
    {
        "question": "Ward 1 Council Member Joe Jones spoke about dire health outcomes in the Lee-Harvard area. How can that be the case with a neighborhood that neighbors the suburbs of Shaker Heights and Warrensville Heights and is near Cleveland Clinic South Pointe Hospital?",
        "sub_topic": "health outcome disparities near medical facilities",
        "description": "The contrast between poor health outcomes in Lee-Harvard and the neighborhood's proximity to suburban wealth and hospital resources.",
        "expected_topics": ["HEALTH"],
        "expected_question_types": ["knowledge_gap", "skepticism"],
    },

    # --- Cleveland City Council Housing Committee (tests/fixtures/hard_case_note.txt) ---
    {
        "question": "How are landlords notified about the new inspection requirements, and what is the enforcement timeline?",
        "sub_topic": "rental inspection notification and enforcement",
        "description": "The process for communicating new inspection requirements to landlords and the timeline for enforcement.",
        "expected_topics": ["HOUSING"],
        "expected_question_types": ["process_confusion", "knowledge_gap"],
    },
    {
        "question": "What funding source is the weatherization pilot drawing from — federal, state, or local?",
        "sub_topic": "weatherization assistance program funding",
        "description": "Which level of government is funding the weatherization pilot program for low-income homeowners.",
        "expected_topics": ["HOUSING", "BUDGET"],
        "expected_question_types": ["knowledge_gap"],
    },
    {
        "question": "Who decides which neighborhoods are eligible for the weatherization pilot?",
        "sub_topic": "weatherization pilot neighborhood eligibility",
        "description": "Decision-making authority over which neighborhoods qualify for the weatherization assistance pilot program.",
        "expected_topics": ["HOUSING"],
        "expected_question_types": ["process_confusion"],
    },
    {
        "question": "Are there appeals for landlords who dispute inspection findings?",
        "sub_topic": "landlord appeal process for housing inspection disputes",
        "description": "Whether a formal appeals process exists for landlords who disagree with housing inspection outcomes.",
        "expected_topics": ["HOUSING"],
        "expected_question_types": ["knowledge_gap", "process_confusion"],
    },
]


# ---------------------------------------------------------------------------
# Dataset management
# ---------------------------------------------------------------------------


def get_or_create_dataset(client):
    """Return the eval dataset, creating it with examples if it doesn't exist."""
    from langsmith.utils import LangSmithNotFoundError

    try:
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        print(f"Using existing dataset '{DATASET_NAME}' ({dataset.id})")
        return dataset
    except Exception:
        pass

    print(f"Creating dataset '{DATASET_NAME}'...")
    dataset = client.create_dataset(
        DATASET_NAME,
        description="Eval dataset for cle-documenters classify_one — question type and topic accuracy.",
    )
    for ex in EXAMPLES:
        client.create_example(
            inputs={
                "question": ex["question"],
                "sub_topic": ex["sub_topic"],
                "description": ex["description"],
            },
            outputs={
                "expected_topics": ex["expected_topics"],
                "expected_question_types": ex["expected_question_types"],
            },
            dataset_id=dataset.id,
        )
    print(f"Created dataset with {len(EXAMPLES)} examples.")
    return dataset


# ---------------------------------------------------------------------------
# Target function
# ---------------------------------------------------------------------------


def target(inputs: dict) -> dict:
    """Run classify_one against a single question and return topic + question_type."""
    from langchain_openai import ChatOpenAI
    from documenters_cle_langchain.classify_themes import classify_one
    from documenters_cle_langchain.extract_candidates import ThemeCandidate
    from documenters_cle_langchain.graph import GraphConfig

    config = GraphConfig()

    candidate = ThemeCandidate(
        doc_id="eval",
        source_question=inputs["question"],
        sub_topic=inputs["sub_topic"],
        description=inputs.get("description", ""),
        retrieved_context=[],  # no library context — cold-start conditions
    )

    # Raw LLMs — classify_one calls bind_tools / with_structured_output internally.
    # On main before issue #60: use merge_llm.with_structured_output(_MergeSplitDecision)
    # and qt_llm.with_structured_output(_QuestionTypeAndTopic) directly.
    merge_llm = ChatOpenAI(model=config.classify_model)
    qt_llm = ChatOpenAI(model=config.question_type_model)

    result = classify_one(
        candidate,
        merge_llm,
        qt_llm,
        review_threshold=config.review_confidence_threshold,
        tools=None,  # no library on cold-start eval
    )

    return {
        "topic": result.topic,
        "question_type": result.question_type or "uncertain",
    }


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------


def topic_evaluator(run, example) -> dict:
    """1 if predicted topic is in the expected set, else 0."""
    predicted = (run.outputs or {}).get("topic", "")
    expected = (example.outputs or {}).get("expected_topics", [])
    match = predicted in expected
    return {
        "key": "topic_match",
        "score": int(match),
        "comment": f"predicted={predicted!r}  acceptable={expected}",
    }


def question_type_evaluator(run, example) -> dict:
    """1 if predicted question type is in the expected set, else 0."""
    predicted = (run.outputs or {}).get("question_type", "")
    expected = (example.outputs or {}).get("expected_question_types", [])
    match = predicted in expected
    return {
        "key": "question_type_match",
        "score": int(match),
        "comment": f"predicted={predicted!r}  acceptable={expected}",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    from langsmith import Client
    from langsmith.evaluation import evaluate

    client = Client()
    dataset = get_or_create_dataset(client)

    from documenters_cle_langchain.graph import GraphConfig

    print(f"\nRunning eval against {len(EXAMPLES)} examples...")
    results = evaluate(
        target,
        data=DATASET_NAME,
        evaluators=[topic_evaluator, question_type_evaluator],
        experiment_prefix="classify-eval",
        max_concurrency=2,
        metadata={"model": GraphConfig().classify_model},
    )

    # Print summary
    scores = {"topic_match": [], "question_type_match": []}
    for r in results:
        for fb in (r.get("feedback") or []):
            key = fb.key if hasattr(fb, "key") else fb.get("key", "")
            score = fb.score if hasattr(fb, "score") else fb.get("score", 0)
            if key in scores:
                scores[key].append(score)

    print("\n--- Eval Summary ---")
    for key, vals in scores.items():
        if vals:
            pct = sum(vals) / len(vals) * 100
            print(f"  {key}: {sum(vals)}/{len(vals)} ({pct:.0f}%)")
    print(f"\nFull results in LangSmith: https://smith.langchain.com")
