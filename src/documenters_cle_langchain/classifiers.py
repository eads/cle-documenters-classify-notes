from __future__ import annotations

from pydantic import BaseModel, Field
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

CIVIC_INFRASTRUCTURE_TOPICS = [
    "stadiums / sports venues",
    "bridges / roads / highways",
    "water treatment / processing",
    "sewers / stormwater",
    "public transit",
    "schools / public buildings",
    "parks / urban forestry",
    "housing / zoning",
    "utilities (electric, gas)",
    "broadband / digital infrastructure",
]

_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """\
You classify public meeting notes to identify discussions of civic infrastructure.

Civic infrastructure includes: {topics}

Respond with JSON only. Be conservative — only mark as civic infrastructure if \
the meeting substantively discusses these topics, not just mentions them in passing.\
"""),
    ("human", """\
Meeting: {meeting_name}
Agency: {agency}

Summary:
{summary}

Notes (excerpt):
{notes_excerpt}
"""),
])


class CivicInfrastructureResult(BaseModel):
    is_civic_infrastructure: bool
    topics_identified: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class CivicInfrastructureClassifier:
    def __init__(self, model: str = "claude-haiku-4-5-20251001") -> None:
        llm = ChatAnthropic(model=model).with_structured_output(CivicInfrastructureResult)
        self._chain = _PROMPT | llm

    def classify(
        self,
        meeting_name: str,
        agency: str,
        summary: str,
        notes: str,
        notes_max_chars: int = 1500,
    ) -> CivicInfrastructureResult:
        return self._chain.invoke({
            "topics": ", ".join(CIVIC_INFRASTRUCTURE_TOPICS),
            "meeting_name": meeting_name,
            "agency": agency,
            "summary": summary,
            "notes_excerpt": notes[:notes_max_chars],
        })
