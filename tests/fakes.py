"""Fakes determinísticos para testar casos de uso sem rede ou custo."""

from collections.abc import AsyncIterator, Sequence

from chatbot.application.models import SourcePage
from chatbot.domain.models import ChatSession, DocumentChunk, Message, RetrievedChunk


class FakeLLM:
    def __init__(self, tokens: Sequence[str] = ("resposta",)) -> None:
        self.tokens = tuple(tokens)
        self.models: list[str] = []
        self.messages: list[tuple[Message, ...]] = []
        self.contexts: list[tuple[DocumentChunk, ...]] = []

    async def stream(
        self,
        *,
        model: str,
        messages: Sequence[Message],
        context: Sequence[DocumentChunk],
    ) -> AsyncIterator[str]:
        self.models.append(model)
        self.messages.append(tuple(messages))
        self.contexts.append(tuple(context))
        for token in self.tokens:
            yield token


class FakeEmbedding:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.inputs.extend(texts)
        return [[float(len(text)), 1.0] for text in texts]


class FakeVectorStore:
    def __init__(self, results: Sequence[RetrievedChunk] = ()) -> None:
        self.results = tuple(results)
        self.stored: dict[str, tuple[DocumentChunk, tuple[float, ...]]] = {}
        self.queries: list[str] = []

    async def search(
        self,
        query: str,
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        self.queries.append(query)
        return tuple(item for item in self.results if item.score >= score_threshold)[:limit]

    async def existing_hashes(self, hashes: Sequence[str]) -> set[str]:
        return {
            content_hash
            for content_hash in hashes
            if any(chunk.content_hash == content_hash for chunk, _ in self.stored.values())
        }

    async def upsert(
        self,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.stored[chunk.id] = (chunk, tuple(vector))


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[str, ChatSession] = {}

    async def get(self, session_id: str) -> ChatSession | None:
        return self.sessions.get(session_id)

    async def save(self, session: ChatSession) -> None:
        self.sessions[session.id] = session

    async def delete(self, session_id: str) -> bool:
        return self.sessions.pop(session_id, None) is not None


class FakeDocumentSource:
    def __init__(self, pages: Sequence[SourcePage]) -> None:
        self.pages = tuple(pages)

    async def load(self) -> Sequence[SourcePage]:
        return self.pages
