"""Tests for classify_themes.py — prompt construction and classification logic.

No real LLM calls. FakeMergeLLM and FakeQTLLM inject preset responses so
all business logic is exercised without OPENAI_API_KEY.
"""
from __future__ import annotations

import pytest

from documenters_cle_langchain.classify_themes import (
    ClassifiedTheme,
    _MergeSplitDecision,
    _QuestionTypeAndTopic,
    _QUESTION_TYPE_DEFS,
    _TOPIC_LIST,
    build_merge_split_prompt,
    build_question_type_prompt,
    classify_one,
    run_classify_themes,
)
from documenters_cle_langchain.extract_candidates import ThemeCandidate
from documenters_cle_langchain.theme_library import QuestionType, Topic


# ---------------------------------------------------------------------------
# Fake LLMs
# ---------------------------------------------------------------------------


class FakeMergeLLM:
    """Fake merge LLM supporting bind_tools and with_structured_output.

    classify_one calls these methods internally rather than invoking the LLM
    directly, so both must be present. bind_tools returns a no-op raw LLM
    that reports zero tool calls; with_structured_output returns the preset
    _MergeSplitDecision response.
    """

    def __init__(self, response: _MergeSplitDecision):
        self.response = response
        self.calls: list[list] = []

    def bind_tools(self, tools: list) -> "_FakeRawMergeLLM":
        return _FakeRawMergeLLM()

    def with_structured_output(self, schema: type) -> "_FakeStructuredMergeLLM":
        return _FakeStructuredMergeLLM(self)


class _FakeRawMergeLLM:
    """Raw fake LLM returned by FakeMergeLLM.bind_tools — never produces tool calls."""

    def invoke(self, messages: list) -> object:
        from unittest.mock import MagicMock
        msg = MagicMock()
        msg.tool_calls = []
        return msg


class _FakeStructuredMergeLLM:
    def __init__(self, parent: FakeMergeLLM):
        self._parent = parent

    def invoke(self, messages: list) -> _MergeSplitDecision:
        self._parent.calls.append(messages)
        return self._parent.response


class FakeQTLLM:
    """Fake question-type LLM supporting with_structured_output."""

    def __init__(self, response: _QuestionTypeAndTopic):
        self.response = response
        self.calls: list[list] = []

    def with_structured_output(self, schema: type) -> "_FakeStructuredQTLLM":
        return _FakeStructuredQTLLM(self)


class _FakeStructuredQTLLM:
    def __init__(self, parent: FakeQTLLM):
        self._parent = parent

    def invoke(self, messages: list) -> _QuestionTypeAndTopic:
        self._parent.calls.append(messages)
        return self._parent.response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DEFAULT_MERGE_RESPONSE = _MergeSplitDecision(
    decision="new",
    matched_theme=None,
    confidence=0.85,
    reasoning="No similar theme found; this is a distinct civic concern.",
)

DEFAULT_QT_RESPONSE = _QuestionTypeAndTopic(
    question_type="knowledge_gap",
    question_type_confidence=0.82,
    low_confidence=False,
    proposed_new_type=None,
    topic="HOUSING",
)

HOUSING_SIMILAR = {
    "sub_topic": "Section 8 voucher waitlists",
    "description": "Long waits for housing vouchers",
    "topic": "HOUSING",
    "similarity_score": 0.91,
}


def make_candidate(
    sub_topic: str = "lead pipe replacement funding",
    description: str = "Funding gaps for replacing lead service lines.",
    source_question: str = "When will the city replace the lead pipes in our neighborhood?",
    doc_id: str = "doc-1",
    retrieved_context: list[dict] | None = None,
) -> ThemeCandidate:
    return ThemeCandidate(
        doc_id=doc_id,
        source_question=source_question,
        sub_topic=sub_topic,
        description=description,
        retrieved_context=retrieved_context or [],
    )


THRESHOLD = 0.4


# ---------------------------------------------------------------------------
# build_merge_split_prompt
# ---------------------------------------------------------------------------


def test_merge_split_prompt_has_two_messages():
    messages = build_merge_split_prompt(make_candidate())
    assert len(messages) == 2


def test_merge_split_prompt_system_first():
    messages = build_merge_split_prompt(make_candidate())
    assert messages[0]["role"] == "system"


def test_merge_split_prompt_user_second():
    messages = build_merge_split_prompt(make_candidate())
    assert messages[1]["role"] == "user"


def test_merge_split_prompt_system_explains_merge():
    messages = build_merge_split_prompt(make_candidate())
    assert "MERGE" in messages[0]["content"]
    assert "NEW" in messages[0]["content"]


def test_merge_split_prompt_system_lean_new():
    """System prompt must instruct model to lean toward NEW when uncertain."""
    messages = build_merge_split_prompt(make_candidate())
    assert "lean toward NEW" in messages[0]["content"]


def test_merge_split_prompt_user_contains_sub_topic():
    candidate = make_candidate(sub_topic="water main breaks")
    messages = build_merge_split_prompt(candidate)
    assert "water main breaks" in messages[1]["content"]


def test_merge_split_prompt_user_contains_description():
    candidate = make_candidate(description="Frequent ruptures in aging water infrastructure.")
    messages = build_merge_split_prompt(candidate)
    assert "Frequent ruptures" in messages[1]["content"]


def test_merge_split_prompt_user_contains_retrieved_themes():
    candidate = make_candidate(retrieved_context=[HOUSING_SIMILAR])
    messages = build_merge_split_prompt(candidate)
    assert "Section 8 voucher waitlists" in messages[1]["content"]


def test_merge_split_prompt_cold_start_message():
    candidate = make_candidate(retrieved_context=[])
    messages = build_merge_split_prompt(candidate)
    assert "new theme" in messages[1]["content"].lower()


# ---------------------------------------------------------------------------
# build_question_type_prompt
# ---------------------------------------------------------------------------


def test_qt_prompt_has_two_messages():
    messages = build_question_type_prompt(make_candidate())
    assert len(messages) == 2


def test_qt_prompt_system_contains_all_question_types():
    messages = build_question_type_prompt(make_candidate())
    for qt in QuestionType:
        assert qt.value in messages[0]["content"]


def test_qt_prompt_system_contains_topic_taxonomy():
    messages = build_question_type_prompt(make_candidate())
    for topic in ["HOUSING", "EDUCATION", "TRANSPORTATION", "BUDGET"]:
        assert topic in messages[0]["content"]


def test_qt_prompt_system_mentions_low_confidence():
    messages = build_question_type_prompt(make_candidate())
    assert "low_confidence" in messages[0]["content"]


def test_qt_prompt_system_mentions_proposed_new_type():
    messages = build_question_type_prompt(make_candidate())
    assert "proposed_new_type" in messages[0]["content"]


def test_qt_prompt_user_contains_question():
    q = "Why hasn't the city replaced the lead pipes yet?"
    candidate = make_candidate(source_question=q)
    messages = build_question_type_prompt(candidate)
    assert q in messages[1]["content"]


def test_qt_prompt_user_contains_sub_topic():
    candidate = make_candidate(sub_topic="lead pipe replacement funding")
    messages = build_question_type_prompt(candidate)
    assert "lead pipe replacement funding" in messages[1]["content"]


# ---------------------------------------------------------------------------
# classify_one — merge/split decisions
# ---------------------------------------------------------------------------


def test_clear_new_case():
    """No retrieved themes → decision=new, high confidence."""
    merge_resp = _MergeSplitDecision(
        decision="new", matched_theme=None, confidence=0.9, reasoning="Novel concern."
    )
    result = classify_one(
        make_candidate(), FakeMergeLLM(merge_resp), FakeQTLLM(DEFAULT_QT_RESPONSE), THRESHOLD
    )
    assert result.decision == "new"
    assert result.matched_theme is None
    assert result.merge_confidence == 0.9


def test_clear_merge_case():
    """Candidate closely matches existing theme → decision=merge, matched_theme set."""
    merge_resp = _MergeSplitDecision(
        decision="merge",
        matched_theme="Section 8 voucher waitlists",
        confidence=0.88,
        reasoning="Same underlying concern about housing voucher access.",
    )
    candidate = make_candidate(
        sub_topic="housing voucher delays",
        retrieved_context=[HOUSING_SIMILAR],
    )
    result = classify_one(
        candidate, FakeMergeLLM(merge_resp), FakeQTLLM(DEFAULT_QT_RESPONSE), THRESHOLD
    )
    assert result.decision == "merge"
    assert result.matched_theme == "Section 8 voucher waitlists"
    assert result.merge_confidence == 0.88


def test_borderline_case_flagged_for_review():
    """Confidence below threshold → needs_review=True."""
    merge_resp = _MergeSplitDecision(
        decision="merge",
        matched_theme="Section 8 voucher waitlists",
        confidence=0.35,  # below 0.4 threshold
        reasoning="Possible overlap but not certain.",
    )
    result = classify_one(
        make_candidate(), FakeMergeLLM(merge_resp), FakeQTLLM(DEFAULT_QT_RESPONSE), THRESHOLD
    )
    assert result.needs_review is True


def test_confident_case_not_flagged():
    """Confidence at or above threshold → needs_review=False."""
    merge_resp = _MergeSplitDecision(
        decision="new", matched_theme=None, confidence=0.4, reasoning="Distinct."
    )
    result = classify_one(
        make_candidate(), FakeMergeLLM(merge_resp), FakeQTLLM(DEFAULT_QT_RESPONSE), THRESHOLD
    )
    assert result.needs_review is False


def test_threshold_boundary_exact():
    """Confidence exactly at threshold is not flagged (threshold is exclusive lower bound)."""
    merge_resp = _MergeSplitDecision(
        decision="new", matched_theme=None, confidence=0.4, reasoning="At boundary."
    )
    result = classify_one(
        make_candidate(), FakeMergeLLM(merge_resp), FakeQTLLM(DEFAULT_QT_RESPONSE), THRESHOLD
    )
    assert result.needs_review is False


def test_merge_reasoning_preserved():
    merge_resp = _MergeSplitDecision(
        decision="new", matched_theme=None, confidence=0.9, reasoning="Unique issue."
    )
    result = classify_one(
        make_candidate(), FakeMergeLLM(merge_resp), FakeQTLLM(DEFAULT_QT_RESPONSE), THRESHOLD
    )
    assert result.merge_reasoning == "Unique issue."


# ---------------------------------------------------------------------------
# classify_one — question type decisions
# ---------------------------------------------------------------------------


def test_question_type_assigned():
    qt_resp = _QuestionTypeAndTopic(
        question_type="accountability",
        question_type_confidence=0.78,
        low_confidence=False,
        proposed_new_type=None,
        topic="HOUSING",
    )
    result = classify_one(
        make_candidate(), FakeMergeLLM(DEFAULT_MERGE_RESPONSE), FakeQTLLM(qt_resp), THRESHOLD
    )
    assert result.question_type == "accountability"
    assert result.question_type_confidence == 0.78
    assert result.question_type_low_confidence is False


def test_question_type_low_confidence_flag_preserved():
    """Low-confidence flag from model must be preserved in ClassifiedTheme."""
    qt_resp = _QuestionTypeAndTopic(
        question_type="skepticism",
        question_type_confidence=0.45,
        low_confidence=True,
        proposed_new_type=None,
        topic="PUBLIC SAFETY",
    )
    result = classify_one(
        make_candidate(), FakeMergeLLM(DEFAULT_MERGE_RESPONSE), FakeQTLLM(qt_resp), THRESHOLD
    )
    assert result.question_type_low_confidence is True
    assert result.question_type == "skepticism"  # still stored, just flagged


def test_question_type_proposed_new_type_preserved():
    """If model proposes a new type, it is stored in proposed_new_question_type."""
    qt_resp = _QuestionTypeAndTopic(
        question_type="uncertain",
        question_type_confidence=0.30,
        low_confidence=True,
        proposed_new_type="anticipatory concern — reporter flags risk before it materializes",
        topic="BUDGET",
    )
    result = classify_one(
        make_candidate(), FakeMergeLLM(DEFAULT_MERGE_RESPONSE), FakeQTLLM(qt_resp), THRESHOLD
    )
    assert result.proposed_new_question_type is not None
    assert "anticipatory" in result.proposed_new_question_type


def test_question_type_uncertain_becomes_none():
    """'uncertain' question_type is normalised to None in ClassifiedTheme."""
    qt_resp = _QuestionTypeAndTopic(
        question_type="uncertain",
        question_type_confidence=0.20,
        low_confidence=True,
        proposed_new_type=None,
        topic="HOUSING",
    )
    result = classify_one(
        make_candidate(), FakeMergeLLM(DEFAULT_MERGE_RESPONSE), FakeQTLLM(qt_resp), THRESHOLD
    )
    assert result.question_type is None


# ---------------------------------------------------------------------------
# classify_one — topic assignment
# ---------------------------------------------------------------------------


def test_topic_assignment_preserved():
    qt_resp = _QuestionTypeAndTopic(
        question_type="knowledge_gap",
        question_type_confidence=0.85,
        low_confidence=False,
        proposed_new_type=None,
        topic="TRANSPORTATION",
    )
    result = classify_one(
        make_candidate(), FakeMergeLLM(DEFAULT_MERGE_RESPONSE), FakeQTLLM(qt_resp), THRESHOLD
    )
    assert result.topic == "TRANSPORTATION"


def test_topic_housing():
    qt_resp = _QuestionTypeAndTopic(
        question_type="knowledge_gap",
        question_type_confidence=0.9,
        low_confidence=False,
        proposed_new_type=None,
        topic="HOUSING",
    )
    result = classify_one(
        make_candidate(), FakeMergeLLM(DEFAULT_MERGE_RESPONSE), FakeQTLLM(qt_resp), THRESHOLD
    )
    assert result.topic == "HOUSING"


# ---------------------------------------------------------------------------
# classify_one — input fields preserved
# ---------------------------------------------------------------------------


def test_doc_id_preserved():
    result = classify_one(
        make_candidate(doc_id="xyz-789"),
        FakeMergeLLM(DEFAULT_MERGE_RESPONSE),
        FakeQTLLM(DEFAULT_QT_RESPONSE),
        THRESHOLD,
    )
    assert result.doc_id == "xyz-789"


def test_source_question_preserved():
    q = "Has the city applied for federal infrastructure funding?"
    result = classify_one(
        make_candidate(source_question=q),
        FakeMergeLLM(DEFAULT_MERGE_RESPONSE),
        FakeQTLLM(DEFAULT_QT_RESPONSE),
        THRESHOLD,
    )
    assert result.source_question == q


def test_retrieved_context_preserved():
    result = classify_one(
        make_candidate(retrieved_context=[HOUSING_SIMILAR]),
        FakeMergeLLM(DEFAULT_MERGE_RESPONSE),
        FakeQTLLM(DEFAULT_QT_RESPONSE),
        THRESHOLD,
    )
    assert len(result.retrieved_context) == 1


def test_result_is_classified_theme_instance():
    result = classify_one(
        make_candidate(),
        FakeMergeLLM(DEFAULT_MERGE_RESPONSE),
        FakeQTLLM(DEFAULT_QT_RESPONSE),
        THRESHOLD,
    )
    assert isinstance(result, ClassifiedTheme)


# ---------------------------------------------------------------------------
# Hard cases — blurry taxonomy edges
# ---------------------------------------------------------------------------

SKEPTICISM_ACCOUNTABILITY_QUESTION = (
    "The city said two years ago they'd replace these pipes — "
    "why hasn't anything happened? Is this just another empty promise?"
)


def test_hard_case_skepticism_accountability_blur_low_confidence():
    """A question blending skepticism and accountability should flag low_confidence."""
    qt_resp = _QuestionTypeAndTopic(
        question_type="accountability",
        question_type_confidence=0.51,
        low_confidence=True,   # model flags the blur
        proposed_new_type=None,
        topic="UTILITIES",
    )
    candidate = make_candidate(source_question=SKEPTICISM_ACCOUNTABILITY_QUESTION)
    result = classify_one(
        candidate, FakeMergeLLM(DEFAULT_MERGE_RESPONSE), FakeQTLLM(qt_resp), THRESHOLD
    )
    assert result.question_type_low_confidence is True
    # A type is still assigned — model picks closest, doesn't refuse
    assert result.question_type is not None


def test_hard_case_no_fitting_label_proposes_new():
    """If no existing label fits, model proposes a new type — that is preserved."""
    qt_resp = _QuestionTypeAndTopic(
        question_type="uncertain",
        question_type_confidence=0.25,
        low_confidence=True,
        proposed_new_type="anticipatory concern — reporter flags a risk before it materializes",
        topic="ENVIRONMENT",
    )
    candidate = make_candidate(
        source_question="What happens if the dam fails during a major storm next year?"
    )
    result = classify_one(
        candidate, FakeMergeLLM(DEFAULT_MERGE_RESPONSE), FakeQTLLM(qt_resp), THRESHOLD
    )
    assert result.proposed_new_question_type is not None
    assert result.question_type is None  # "uncertain" → None


# ---------------------------------------------------------------------------
# run_classify_themes
# ---------------------------------------------------------------------------


def test_empty_candidates_returns_empty():
    classified, needs_review = run_classify_themes(
        [], FakeMergeLLM(DEFAULT_MERGE_RESPONSE), FakeQTLLM(DEFAULT_QT_RESPONSE), THRESHOLD
    )
    assert classified == []
    assert needs_review == []


def test_produces_one_classified_per_candidate():
    candidates = [make_candidate(doc_id=f"d{i}") for i in range(3)]
    classified, _ = run_classify_themes(
        candidates,
        FakeMergeLLM(DEFAULT_MERGE_RESPONSE),
        FakeQTLLM(DEFAULT_QT_RESPONSE),
        THRESHOLD,
    )
    assert len(classified) == 3


def test_needs_review_subset_only_flagged():
    """needs_review contains only items with needs_review=True."""
    responses = [
        _MergeSplitDecision(decision="new", matched_theme=None, confidence=0.9, reasoning=""),
        _MergeSplitDecision(decision="merge", matched_theme="x", confidence=0.2, reasoning=""),
        _MergeSplitDecision(decision="new", matched_theme=None, confidence=0.8, reasoning=""),
    ]

    class SequentialMergeLLM:
        def __init__(self):
            self._i = 0

        def bind_tools(self, tools):
            return _FakeRawMergeLLM()

        def with_structured_output(self, schema):
            outer = self
            class _S:
                def invoke(self_, msgs):
                    r = responses[outer._i]
                    outer._i += 1
                    return r
            return _S()

    candidates = [make_candidate(doc_id=f"d{i}") for i in range(3)]
    classified, needs_review = run_classify_themes(
        candidates, SequentialMergeLLM(), FakeQTLLM(DEFAULT_QT_RESPONSE), THRESHOLD
    )
    assert len(classified) == 3
    assert len(needs_review) == 1
    assert needs_review[0].merge_confidence == 0.2


def test_needs_review_threshold_configurable():
    """Raising the threshold flags more items for review."""
    merge_resp = _MergeSplitDecision(
        decision="new", matched_theme=None, confidence=0.55, reasoning=""
    )
    candidates = [make_candidate()]

    _, needs_review_low = run_classify_themes(
        candidates, FakeMergeLLM(merge_resp), FakeQTLLM(DEFAULT_QT_RESPONSE), review_threshold=0.4
    )
    _, needs_review_high = run_classify_themes(
        candidates, FakeMergeLLM(merge_resp), FakeQTLLM(DEFAULT_QT_RESPONSE), review_threshold=0.6
    )

    assert len(needs_review_low) == 0   # 0.55 >= 0.4 → not flagged
    assert len(needs_review_high) == 1  # 0.55 < 0.6 → flagged


def test_llm_called_twice_per_candidate():
    """Both merge LLM and QT LLM are called once per candidate."""
    merge_llm = FakeMergeLLM(DEFAULT_MERGE_RESPONSE)
    qt_llm = FakeQTLLM(DEFAULT_QT_RESPONSE)
    candidates = [make_candidate(doc_id=f"d{i}") for i in range(2)]
    run_classify_themes(candidates, merge_llm, qt_llm, THRESHOLD)
    assert len(merge_llm.calls) == 2
    assert len(qt_llm.calls) == 2


# ---------------------------------------------------------------------------
# Tool binding
# ---------------------------------------------------------------------------


def test_classify_one_with_no_tools_uses_structured_output_path():
    """tools=None → structured output is still called, result is correct."""
    result = classify_one(
        make_candidate(), FakeMergeLLM(DEFAULT_MERGE_RESPONSE), FakeQTLLM(DEFAULT_QT_RESPONSE), THRESHOLD
    )
    assert result.decision == DEFAULT_MERGE_RESPONSE.decision


def test_classify_one_tools_bound_but_no_tool_call():
    """When tools are bound but the LLM makes no tool calls, result is unchanged."""
    from unittest.mock import MagicMock

    class _FakeTool:
        name = "search_theme_library"
        def invoke(self, args):
            return "Housing voucher delays — long waits (HOUSING)"

    result = classify_one(
        make_candidate(),
        FakeMergeLLM(DEFAULT_MERGE_RESPONSE),
        FakeQTLLM(DEFAULT_QT_RESPONSE),
        THRESHOLD,
        tools=[_FakeTool()],
    )
    assert result.decision == DEFAULT_MERGE_RESPONSE.decision
    assert result.merge_confidence == DEFAULT_MERGE_RESPONSE.confidence


def test_classify_one_tool_call_appends_tool_message_to_messages():
    """When the raw LLM returns a tool call, the tool is invoked and messages are extended."""
    from langchain_core.messages import ToolMessage

    tool_result_text = "1. affordable housing vouchers — Housing voucher program (HOUSING)"

    class _FakeTool:
        name = "search_theme_library"
        def invoke(self, args):
            return tool_result_text

    # Override bind_tools to return a raw LLM that DOES produce a tool call
    class _MergeLLMWithToolCall(FakeMergeLLM):
        def bind_tools(self, tools):
            return _RawLLMWithToolCall()

    class _RawLLMWithToolCall:
        def invoke(self, messages):
            msg = MagicMock()
            msg.tool_calls = [{"name": "search_theme_library", "args": {"query": "housing"}, "id": "tc-1"}]
            return msg

    from unittest.mock import MagicMock

    merge_llm = _MergeLLMWithToolCall(DEFAULT_MERGE_RESPONSE)
    result = classify_one(
        make_candidate(), merge_llm, FakeQTLLM(DEFAULT_QT_RESPONSE), THRESHOLD,
        tools=[_FakeTool()],
    )
    # After tool call, the augmented messages are passed to with_structured_output
    # The final call includes the tool result in the messages
    assert len(merge_llm.calls) == 1
    augmented_messages = merge_llm.calls[0]
    # Should include the tool message
    assert any(isinstance(m, ToolMessage) for m in augmented_messages)
    tool_msgs = [m for m in augmented_messages if isinstance(m, ToolMessage)]
    assert tool_result_text in tool_msgs[0].content
