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

_PROMPT = ChatPromptTemplate.from_messages([
    ("system", f"""\
You classify public meeting summaries into topic categories.

For each category, return a score from 0.0 to 1.0:
  0.0 = not discussed at all
  0.5 = mentioned in passing
  1.0 = substantively discussed

Also list any specific topics identified (empty list if none).

Categories:
{_CATEGORY_BLOCK}
"""),
    ("human", """\
Meeting: {meeting_name}
Agency: {agency}

Summary:
{summary}
"""),
])


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class MeetingClassifier:
    """Classifies a meeting summary across all configured topic categories."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        llm = ChatOpenAI(model=model).with_structured_output(
            TopicsResult, method="json_schema", strict=True
        )
        self._chain = _PROMPT | llm

    def classify(
        self,
        meeting_name: str,
        agency: str,
        summary: str,
    ) -> TopicsResult:
        return self._chain.invoke({
            "meeting_name": meeting_name,
            "agency": agency,
            "summary": summary,
        })
