from __future__ import annotations

import warnings

# LangChain serializes raw OpenAI response objects through Pydantic internals,
# triggering a spurious warning about the `parsed` field. The data is correct.
warnings.filterwarnings(
    "ignore",
    message="Pydantic serializer warnings",
    category=UserWarning,
    module="pydantic",
)

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


# ---------------------------------------------------------------------------
# Category configuration
# Each entry: (slug, label, description)
# Add new categories here — no other code changes needed.
# ---------------------------------------------------------------------------

CATEGORIES: list[tuple[str, str, str]] = [
    (
        "infrastructure",
        "Civic Infrastructure",
        "stadiums, sports venues, bridges, roads, water treatment, sewers, "
        "public transit, utilities (electric, gas), broadband, parks, urban forestry",
    ),
    (
        "schools",
        "Schools & Education",
        "public schools, school board decisions, closures, budgets, curricula, "
        "school construction or renovation, CMSD, charter schools",
    ),
]


# ---------------------------------------------------------------------------
# Pydantic output schema
# One CategoryResult field per category defined above.
# ---------------------------------------------------------------------------

class CategoryResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)  # 0 = not relevant, 1 = definitely relevant
    identified: list[str] = Field(default_factory=list)


class TopicsResult(BaseModel):
    infrastructure: CategoryResult
    schools: CategoryResult


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_CATEGORY_BLOCK = "\n".join(
    f"- {label} ({slug}): {desc}"
    for slug, label, desc in CATEGORIES
)

AMBIGUOUS_LO = 0.3
AMBIGUOUS_HI = 0.7

_SYSTEM_PROMPT = f"""\
You classify public meeting summaries into topic categories.

For each category, score relevance from 0.0 (not mentioned) to 1.0 (primary focus).
Score in increments of 0.1. Do not limit yourself to 0, 0.5, or 1 —
most meetings will have nuanced scores like 0.2, 0.4, 0.7, 0.9.

Also list any specific topics identified (empty list if none).

Categories:
{_CATEGORY_BLOCK}
"""

_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_PROMPT),
    ("human", """\
Meeting: {meeting_name}
Agency: {agency}

Summary:
{summary}

Follow-up Questions:
{follow_up_questions}

Single Signal:
{single_signal}
"""),
])

_PROMPT_FULL = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_PROMPT),
    ("human", """\
Meeting: {meeting_name}
Agency: {agency}

Summary:
{summary}

Follow-up Questions:
{follow_up_questions}

Single Signal:
{single_signal}

Full Notes:
{notes}
"""),
])


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class MeetingClassifier:
    """Classifies a meeting summary across all configured topic categories.

    Initial pass uses summary + follow_up_questions + single_signal.
    If any category score is ambiguous ([AMBIGUOUS_LO, AMBIGUOUS_HI]),
    a fallback pass feeds the full notes to a stronger model.
    """

    def __init__(self, model: str = "gpt-5-mini", fallback_model: str = "gpt-5.4") -> None:
        self.model = model
        self.fallback_model = fallback_model
        llm = ChatOpenAI(model=model).with_structured_output(
            TopicsResult, method="json_schema", strict=True
        )
        self._chain = _PROMPT | llm
        fallback_llm = ChatOpenAI(model=fallback_model).with_structured_output(
            TopicsResult, method="json_schema", strict=True
        )
        self._fallback_chain = _PROMPT_FULL | fallback_llm

    def classify(
        self,
        meeting_name: str,
        agency: str,
        summary: str,
        follow_up_questions: str = "",
        single_signal: str = "",
    ) -> TopicsResult:
        return self._chain.invoke({
            "meeting_name": meeting_name,
            "agency": agency,
            "summary": summary,
            "follow_up_questions": follow_up_questions,
            "single_signal": single_signal,
        })

    def classify_full(
        self,
        meeting_name: str,
        agency: str,
        summary: str,
        follow_up_questions: str = "",
        single_signal: str = "",
        notes: str = "",
    ) -> TopicsResult:
        return self._fallback_chain.invoke({
            "meeting_name": meeting_name,
            "agency": agency,
            "summary": summary,
            "follow_up_questions": follow_up_questions,
            "single_signal": single_signal,
            "notes": notes,
        })

    @staticmethod
    def is_ambiguous(result: TopicsResult) -> bool:
        """True if any category score falls in the ambiguous band [LO, HI]."""
        return any(
            AMBIGUOUS_LO <= cat["score"] <= AMBIGUOUS_HI
            for cat in result.model_dump().values()
        )
