"""Fakes determinísticos para testar casos de uso sem rede ou custo."""

from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import contextmanager

from chatbot.application.models import PromptMessage, SourcePage
from chatbot.application.observability import ChatObservation
from chatbot.domain.models import ChatSession, DocumentChunk, RetrievedChunk


class FakeLLM:
    """LLM determinístico que registra modelo e prompt recebidos."""

    def __init__(self, tokens: Sequence[str] = ("resposta",)) -> None:
        self.tokens = tuple(tokens)
        self.models: list[str] = []
        self.messages: list[tuple[PromptMessage, ...]] = []

    async def stream(
        self,
        *,
        model: str,
        messages: Sequence[PromptMessage],
    ) -> AsyncIterator[str]:
        """Emite os tokens configurados e guarda o que o caso de uso enviou."""
        self.models.append(model)
        self.messages.append(tuple(messages))
        for token in self.tokens:
            yield token


class FakeEmbedding:
    """Embedding local baseado no comprimento do texto, sem rede."""

    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Registra as entradas e devolve um vetor previsível por texto."""
        self.inputs.extend(texts)
        return [[float(len(text)), 1.0] for text in texts]


class FakeVectorStore:
    """Índice em memória usado tanto na recuperação quanto na ingestão."""

    def __init__(self, results: Sequence[RetrievedChunk] = ()) -> None:
        self.results = tuple(results)
        self.stored: dict[str, tuple[DocumentChunk, tuple[float, ...]]] = {}
        self.queries: list[str] = []
        self.indexes_ensured = False

    async def ensure_indexes(self) -> None:
        """Marca que a ingestão pediu a criação dos índices."""
        self.indexes_ensured = True

    async def search(
        self,
        query: str,
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        """Filtra os resultados pré-carregados pelo limiar e pelo limite."""
        self.queries.append(query)
        return tuple(item for item in self.results if item.score >= score_threshold)[:limit]

    async def existing_hashes(self, hashes: Sequence[str]) -> set[str]:
        """Informa quais hashes já foram persistidos neste fake."""
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
        """Guarda trechos e vetores para asserções da ingestão."""
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.stored[chunk.id] = (chunk, tuple(vector))


class FakeSessionRepository:
    """Repositório volátil que expõe o dicionário interno aos testes."""

    def __init__(self) -> None:
        self.sessions: dict[str, ChatSession] = {}

    async def get(self, session_id: str) -> ChatSession | None:
        """Devolve uma cópia da sessão para isolar o estado armazenado."""
        stored = self.sessions.get(session_id)
        return None if stored is None else stored.copy()

    async def save(self, session: ChatSession) -> None:
        """Guarda uma cópia isolada da sessão recebida."""
        self.sessions[session.id] = session.copy()

    async def delete(self, session_id: str) -> bool:
        """Remove a sessão e informa se ela existia."""
        return self.sessions.pop(session_id, None) is not None


class FakeDocumentSource:
    """Origem documental com páginas pré-definidas."""

    def __init__(self, pages: Sequence[SourcePage]) -> None:
        self.pages = tuple(pages)

    async def load(self) -> Sequence[SourcePage]:
        """Devolve as páginas configuradas no construtor."""
        return self.pages


class CharacterEncoding:
    """Tokenização 1:1 por caractere para testes de chunking."""

    def encode(self, text: str) -> list[int]:
        """Um token por caractere, suficiente para testes de janela."""
        return [ord(character) for character in text]

    def decode(self, tokens: Sequence[int]) -> str:
        """Reconstrói o texto a partir dos códigos dos caracteres."""
        return "".join(chr(token) for token in tokens)


class _RecordingSpan:
    def __init__(self, attributes: dict[str, str | int | float | bool]) -> None:
        self._attributes = attributes

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        self._attributes[key] = value


class RecordingObservability:
    """Guarda intervalos e desfechos para asserções sem exportar telemetria."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str | int | float | bool]]] = []
        self.observations: list[ChatObservation] = []
        self.rejections: list[tuple[str, str]] = []

    @contextmanager
    def start_span(
        self,
        name: str,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> Iterator[_RecordingSpan]:
        """Memoriza o intervalo e permite anotações posteriores no mesmo mapa."""
        stored = dict(attributes or {})
        self.spans.append((name, stored))
        yield _RecordingSpan(stored)

    def record_chat(self, observation: ChatObservation) -> None:
        """Guarda o desfecho informado pelo adapter HTTP."""
        self.observations.append(observation)

    def record_admission_rejected(
        self,
        *,
        request_id: str,
        session_fingerprint: str,
    ) -> None:
        """Guarda a recusa de admissão para o teste de saturação."""
        self.rejections.append((request_id, session_fingerprint))
