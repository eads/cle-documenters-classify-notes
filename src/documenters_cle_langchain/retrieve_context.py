"""retrieve_context.py — semantic retrieval from the Theme Library.

Builds an ephemeral InMemoryVectorStore from ThemeRecords at run start.
Queries per follow-up question to find semantically similar past themes.
Called by the `retrieve_context` node in graph.py.

The vector store is ephemeral — rebuilt from Google Sheets at the start of
each run and discarded at the end. Sheets is the persistence layer; this is
the runtime retrieval index.

The venue/institutional context slot is stubbed as a no-op. It is wired into
the output type now so downstream nodes have a stable contract, but no
retrieval is performed until the Meeting/Venue Knowledge Base is in scope.
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.vectorstores import InMemoryVectorStore

from .ingest import IngestedDoc
from .theme_library import ThemeRecord

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


class SimilarTheme(TypedDict):
    """A retrieved theme from the library, with its similarity score."""

    sub_topic: str
    description: str
    topic: str
    similarity_score: float


class QuestionContext(TypedDict):
    """Retrieval context for a single follow-up question.

    ``similar_themes`` holds the top-k themes from the Theme Library ordered
    by semantic similarity. Empty list on cold start (no library yet).

    ``venue_context`` is reserved for the future Meeting/Venue Knowledge Base;
    always empty for now.
    """

    doc_id: str
    question: str
    similar_themes: list[SimilarTheme]
    venue_context: list[Any]  # stub — always [] until venue KB is in scope


# ---------------------------------------------------------------------------
# Vector store construction
# ---------------------------------------------------------------------------


def build_vector_store(
    themes: list[ThemeRecord],
    embeddings: Any,  # langchain Embeddings instance; not called if themes is empty
) -> InMemoryVectorStore | None:
    """Embed ThemeRecords into an InMemoryVectorStore.

    Returns None on cold start (empty theme library) without calling the
    embeddings object. The caller is responsible for passing a valid Embeddings
    instance when themes is non-empty.

    Each theme is embedded as "{sub_topic}: {description}". Stored metadata
    includes sub_topic, description, and topic for retrieval display.

    Args:
        themes: confirmed themes from the Theme Library.
        embeddings: langchain Embeddings instance (only called if themes is non-empty).

    Returns:
        Populated InMemoryVectorStore, or None if themes is empty.
    """
    if not themes:
        log.info("retrieve_context: cold start — no themes to index")
        return None

    store = InMemoryVectorStore(embedding=embeddings)
    texts = [f"{t.sub_topic}: {t.description}" for t in themes]
    metadatas = [
        {
            "sub_topic": t.sub_topic,
            "description": t.description,
            "topic": t.topic.value,
        }
        for t in themes
    ]
    store.add_texts(texts, metadatas=metadatas)
    log.info("retrieve_context: indexed %d themes", len(themes))
    return store


# ---------------------------------------------------------------------------
# Per-question retrieval
# ---------------------------------------------------------------------------


def retrieve_for_question(
    question: str,
    store: InMemoryVectorStore | None,
    k: int,
) -> list[SimilarTheme]:
    """Retrieve top-k similar themes for a single follow-up question.

    Returns empty list on cold start (store is None). If k exceeds the number
    of indexed themes, returns all available themes without error.

    Args:
        question: the follow-up question text.
        store: the vector store (None = cold start).
        k: number of similar themes to retrieve.

    Returns:
        List of SimilarTheme dicts, ordered by similarity score descending.
    """
    if store is None:
        return []

    results = store.similarity_search_with_score(question, k=k)
    similar: list[SimilarTheme] = []
    for doc, score in results:
        similar.append(
            SimilarTheme(
                sub_topic=doc.metadata["sub_topic"],
                description=doc.metadata["description"],
                topic=doc.metadata["topic"],
                similarity_score=float(score),
            )
        )
    log.debug(
        "retrieve: '%s…' → %d similar (scores: %s)",
        question[:50],
        len(similar),
        [f"{s['similarity_score']:.3f}" for s in similar],
    )
    return similar


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_retrieve_context(
    ingested_docs: list[IngestedDoc],
    theme_library: list[ThemeRecord],
    embeddings: Any | None,
    k: int,
) -> list[QuestionContext]:
    """Build vector store and retrieve similar themes for every follow-up question.

    Produces one QuestionContext per follow-up question across all ingested docs.
    Cold start (empty theme_library or embeddings=None) returns QuestionContexts
    with empty similar_themes — no error.

    Args:
        ingested_docs: gate-passed documents with parsed questions.
        theme_library: confirmed themes (may be empty on cold start).
        embeddings: langchain Embeddings instance, or None for cold start.
        k: number of similar themes to retrieve per question.

    Returns:
        One QuestionContext per follow-up question, in document order.
    """
    store = build_vector_store(theme_library, embeddings)

    contexts: list[QuestionContext] = []
    for doc in ingested_docs:
        for question in doc["follow_up_questions"]:
            similar = retrieve_for_question(question, store, k)
            contexts.append(
                QuestionContext(
                    doc_id=doc["doc_id"],
                    question=question,
                    similar_themes=similar,
                    venue_context=[],  # stub — venue KB not yet in scope
                )
            )

    log.info(
        "retrieve_context: %d questions across %d docs — %d total similar theme hits",
        len(contexts),
        len(ingested_docs),
        sum(len(c["similar_themes"]) for c in contexts),
    )
    return contexts
