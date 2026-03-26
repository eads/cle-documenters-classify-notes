"""Tests for extract_candidates.py — prompt construction and candidate extraction.

No real LLM calls. FakeLLM injects preset _ExtractedTheme responses so
run_extract_candidates can be exercised without OPENAI_API_KEY.
"""
from __future__ import annotations

import pytest

from documenters_cle_langchain.extract_candidates import (
    ThemeCandidate,
    _ExtractedTheme,
    _SingleTheme,
    _format_similar_themes,
    build_extraction_prompt,
    run_extract_candidates,
)
from documenters_cle_langchain.retrieve_context import QuestionContext, SimilarTheme


# ---------------------------------------------------------------------------
# Fake LLM — returns a preset _ExtractedTheme without any API call
# ---------------------------------------------------------------------------


class FakeLLM:
    """Minimal fake that satisfies the llm.invoke(messages) interface."""

    def __init__(self, response: _ExtractedTheme):
        self.response = response
        self.calls: list[list[dict]] = []  # capture inputs for assertion

    def invoke(self, messages: list[dict]) -> _ExtractedTheme:
        self.calls.append(messages)
        return self.response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_similar_theme(sub_topic: str, description: str, topic: str = "HOUSING") -> SimilarTheme:
    return SimilarTheme(
        sub_topic=sub_topic,
        description=description,
        topic=topic,
        similarity_score=0.85,
    )


def make_context(
    doc_id: str,
    question: str,
    similar_themes: list[SimilarTheme] | None = None,
) -> QuestionContext:
    return QuestionContext(
        doc_id=doc_id,
        question=question,
        similar_themes=similar_themes or [],
        venue_context=[],
    )


HOUSING_THEME = make_similar_theme(
    "Section 8 voucher waitlists",
    "Long waits for housing assistance vouchers",
    "HOUSING",
)
EDUCATION_THEME = make_similar_theme(
    "Magnet school enrollment caps",
    "Limits on enrollment at magnet schools",
    "EDUCATION",
)

DEFAULT_RESPONSE = _ExtractedTheme(themes=[
    _SingleTheme(
        sub_topic="Section 8 voucher waitlists",
        description="Community members face long waits for housing vouchers.",
    )
])

# ---------------------------------------------------------------------------
# _format_similar_themes
# ---------------------------------------------------------------------------


def test_format_similar_themes_empty_returns_cold_start_message():
    result = _format_similar_themes([])
    assert "new sub-topic" in result.lower()


def test_format_similar_themes_includes_sub_topic():
    result = _format_similar_themes([HOUSING_THEME])
    assert "Section 8 voucher waitlists" in result


def test_format_similar_themes_includes_description():
    result = _format_similar_themes([HOUSING_THEME])
    assert "Long waits for housing assistance vouchers" in result


def test_format_similar_themes_includes_topic():
    result = _format_similar_themes([HOUSING_THEME])
    assert "HOUSING" in result


def test_format_similar_themes_multiple_numbered():
    result = _format_similar_themes([HOUSING_THEME, EDUCATION_THEME])
    assert "1." in result
    assert "2." in result


# ---------------------------------------------------------------------------
# build_extraction_prompt — structure
# ---------------------------------------------------------------------------


def test_prompt_has_two_messages():
    messages = build_extraction_prompt("What about housing?", [])
    assert len(messages) == 2


def test_prompt_first_message_is_system():
    messages = build_extraction_prompt("What about housing?", [])
    assert messages[0]["role"] == "system"


def test_prompt_second_message_is_user():
    messages = build_extraction_prompt("What about housing?", [])
    assert messages[1]["role"] == "user"


def test_prompt_system_defines_sub_topic():
    messages = build_extraction_prompt("What about housing?", [])
    assert "sub-topic" in messages[0]["content"].lower()


def test_prompt_system_includes_examples():
    """System prompt must include concrete examples so the model understands specificity."""
    messages = build_extraction_prompt("What about housing?", [])
    # At least one of the canonical examples should appear
    assert any(
        example in messages[0]["content"]
        for example in ["Section 8", "enrollment caps", "Lead pipe"]
    )


# ---------------------------------------------------------------------------
# build_extraction_prompt — question and context content
# ---------------------------------------------------------------------------


def test_prompt_contains_question_text():
    question = "Why is the waitlist for housing vouchers so long?"
    messages = build_extraction_prompt(question, [])
    assert question in messages[1]["content"]


def test_prompt_contains_retrieved_theme_label():
    messages = build_extraction_prompt("housing question", [HOUSING_THEME])
    assert "Section 8 voucher waitlists" in messages[1]["content"]


def test_prompt_contains_retrieved_theme_topic():
    messages = build_extraction_prompt("housing question", [HOUSING_THEME])
    assert "HOUSING" in messages[1]["content"]


def test_prompt_cold_start_message_present():
    messages = build_extraction_prompt("housing question", [])
    assert "new sub-topic" in messages[1]["content"].lower()


def test_prompt_multiple_themes_all_appear():
    messages = build_extraction_prompt("question", [HOUSING_THEME, EDUCATION_THEME])
    content = messages[1]["content"]
    assert "Section 8 voucher waitlists" in content
    assert "Magnet school enrollment caps" in content


# ---------------------------------------------------------------------------
# run_extract_candidates — empty / cold start
# ---------------------------------------------------------------------------


def test_empty_retrieval_context_returns_empty_candidates():
    llm = FakeLLM(DEFAULT_RESPONSE)
    candidates = run_extract_candidates([], llm)
    assert candidates == []
    assert llm.calls == []  # LLM never called


# ---------------------------------------------------------------------------
# run_extract_candidates — one LLM call per question
# ---------------------------------------------------------------------------


def test_at_least_one_candidate_per_question():
    contexts = [
        make_context("doc1", "Question one?"),
        make_context("doc1", "Question two?"),
        make_context("doc2", "Question three?"),
    ]
    llm = FakeLLM(DEFAULT_RESPONSE)
    candidates = run_extract_candidates(contexts, llm)
    assert len(candidates) >= 3


def test_llm_called_once_per_question():
    contexts = [
        make_context("doc1", "Q1?"),
        make_context("doc1", "Q2?"),
    ]
    llm = FakeLLM(DEFAULT_RESPONSE)
    run_extract_candidates(contexts, llm)
    assert len(llm.calls) == 2


def test_candidate_order_matches_context_order():
    responses = [
        _ExtractedTheme(themes=[_SingleTheme(sub_topic="first theme", description="first")]),
        _ExtractedTheme(themes=[_SingleTheme(sub_topic="second theme", description="second")]),
    ]

    class SequentialFakeLLM:
        def __init__(self):
            self._idx = 0

        def invoke(self, messages):
            resp = responses[self._idx]
            self._idx += 1
            return resp

    contexts = [
        make_context("doc1", "Q1?"),
        make_context("doc1", "Q2?"),
    ]
    candidates = run_extract_candidates(contexts, SequentialFakeLLM())
    assert candidates[0].sub_topic == "first theme"
    assert candidates[1].sub_topic == "second theme"


# ---------------------------------------------------------------------------
# run_extract_candidates — ThemeCandidate field population
# ---------------------------------------------------------------------------


def test_candidate_doc_id_preserved():
    ctx = make_context("abc-123", "Question?")
    candidates = run_extract_candidates([ctx], FakeLLM(DEFAULT_RESPONSE))
    assert candidates[0].doc_id == "abc-123"


def test_candidate_source_question_preserved():
    question = "Why is the voucher waitlist so long?"
    ctx = make_context("doc1", question)
    candidates = run_extract_candidates([ctx], FakeLLM(DEFAULT_RESPONSE))
    assert candidates[0].source_question == question


def test_candidate_sub_topic_from_llm():
    response = _ExtractedTheme(themes=[_SingleTheme(sub_topic="lead pipe replacement", description="desc")])
    ctx = make_context("doc1", "Question?")
    candidates = run_extract_candidates([ctx], FakeLLM(response))
    assert candidates[0].sub_topic == "lead pipe replacement"


def test_candidate_description_from_llm():
    response = _ExtractedTheme(themes=[_SingleTheme(sub_topic="label", description="Custom description text.")])
    ctx = make_context("doc1", "Question?")
    candidates = run_extract_candidates([ctx], FakeLLM(response))
    assert candidates[0].description == "Custom description text."


def test_candidate_retrieved_context_preserved():
    ctx = make_context("doc1", "Question?", similar_themes=[HOUSING_THEME])
    candidates = run_extract_candidates([ctx], FakeLLM(DEFAULT_RESPONSE))
    assert len(candidates[0].retrieved_context) == 1
    assert candidates[0].retrieved_context[0]["sub_topic"] == "Section 8 voucher waitlists"


def test_candidate_retrieved_context_empty_on_cold_start():
    ctx = make_context("doc1", "Question?", similar_themes=[])
    candidates = run_extract_candidates([ctx], FakeLLM(DEFAULT_RESPONSE))
    assert candidates[0].retrieved_context == []


def test_candidate_is_theme_candidate_instance():
    ctx = make_context("doc1", "Question?")
    candidates = run_extract_candidates([ctx], FakeLLM(DEFAULT_RESPONSE))
    assert isinstance(candidates[0], ThemeCandidate)


# ---------------------------------------------------------------------------
# Hard case — ambiguous question spanning two sub-topics
# ---------------------------------------------------------------------------

AMBIGUOUS_QUESTION = (
    "How does the shortage of Section 8 vouchers affect where families can afford "
    "to live, and does that limit which schools their kids can attend?"
)


def test_hard_case_ambiguous_question_can_produce_multiple_candidates():
    """A question spanning housing and education may produce two candidates.

    The multi-subtopic path must work end-to-end: one LLM call, two candidates
    with the same source question and retrieved_context.
    """
    response = _ExtractedTheme(themes=[
        _SingleTheme(
            sub_topic="Section 8 voucher availability",
            description="Shortage of housing vouchers constrains where families can live.",
        ),
        _SingleTheme(
            sub_topic="school access limited by housing instability",
            description="Families' school choices are restricted by where they can afford to live.",
        ),
    ])
    ctx = make_context(
        "doc1",
        AMBIGUOUS_QUESTION,
        similar_themes=[HOUSING_THEME, EDUCATION_THEME],
    )
    llm = FakeLLM(response)
    candidates = run_extract_candidates([ctx], llm)
    assert len(candidates) == 2
    assert llm.calls  # LLM was called exactly once
    assert len(llm.calls) == 1


def test_hard_case_multi_candidate_shares_source_question():
    """Both candidates from a multi-topic question carry the verbatim question."""
    response = _ExtractedTheme(themes=[
        _SingleTheme(sub_topic="housing", description="desc1"),
        _SingleTheme(sub_topic="education", description="desc2"),
    ])
    ctx = make_context("doc1", AMBIGUOUS_QUESTION)
    candidates = run_extract_candidates([ctx], FakeLLM(response))
    for c in candidates:
        assert c.source_question == AMBIGUOUS_QUESTION


def test_hard_case_multi_candidate_shares_doc_id():
    """Both candidates from a multi-topic question carry the same doc_id."""
    response = _ExtractedTheme(themes=[
        _SingleTheme(sub_topic="housing", description="desc1"),
        _SingleTheme(sub_topic="education", description="desc2"),
    ])
    ctx = make_context("doc-xyz", AMBIGUOUS_QUESTION)
    candidates = run_extract_candidates([ctx], FakeLLM(response))
    for c in candidates:
        assert c.doc_id == "doc-xyz"


def test_hard_case_source_question_preserved_verbatim():
    """The verbatim question is stored even for multi-topic edge cases."""
    ctx = make_context("doc1", AMBIGUOUS_QUESTION)
    candidates = run_extract_candidates([ctx], FakeLLM(DEFAULT_RESPONSE))
    assert candidates[0].source_question == AMBIGUOUS_QUESTION


def test_hard_case_prompt_includes_both_retrieved_themes():
    """Both retrieved themes appear in the prompt so the model has full context."""
    messages = build_extraction_prompt(
        AMBIGUOUS_QUESTION, [HOUSING_THEME, EDUCATION_THEME]
    )
    content = messages[1]["content"]
    assert "Section 8 voucher waitlists" in content
    assert "Magnet school enrollment caps" in content
