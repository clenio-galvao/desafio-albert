from dataclasses import FrozenInstanceError

import pytest

from chatbot.adapters.outbound.documents import resolve_document_title
from chatbot.application import (
    ChatEvent,
    ChatEventType,
    ChatRequest,
    IngestionResult,
    SourcePage,
    UnsupportedModelError,
)
from chatbot.application.use_cases import EndSessionService, ModelCatalog, ReadinessService
from chatbot.domain import ChatSession

from ..fakes import FakeSessionRepository


def test_model_catalog_lists_normalized_unique_models() -> None:
    catalog = ModelCatalog([" model-a ", "model-b", "model-a", " "])

    assert catalog.execute() == ("model-a", "model-b")


def test_model_catalog_accepts_supported_model() -> None:
    ModelCatalog(["model-a", "model-b"]).ensure_supported("model-b")


def test_model_catalog_rejects_empty_configuration() -> None:
    with pytest.raises(ValueError, match="ao menos um"):
        ModelCatalog([" ", ""])


def test_model_catalog_rejects_unsupported_model() -> None:
    catalog = ModelCatalog(["model-a"])

    with pytest.raises(UnsupportedModelError, match="model-b"):
        catalog.ensure_supported("model-b")


async def test_end_session_service_hides_repository_from_input_adapter() -> None:
    sessions = FakeSessionRepository()
    await sessions.save(ChatSession(id="session", max_messages=2))

    deleted = await EndSessionService(sessions).execute("session")

    assert deleted is True
    assert await sessions.get("session") is None


class ReadinessDependency:
    def __init__(self, result: bool = True, error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    async def ready(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.parametrize(
    ("dependency", "expected"),
    [
        (ReadinessDependency(True), True),
        (ReadinessDependency(False), False),
        (ReadinessDependency(error=RuntimeError("offline")), False),
    ],
)
async def test_readiness_service_translates_dependency_state(
    dependency: ReadinessDependency,
    expected: bool,
) -> None:
    assert await ReadinessService(dependency).execute() is expected


def test_chat_request_is_immutable() -> None:
    request = ChatRequest(session_id="session", message="pergunta", model="model-a")

    with pytest.raises(FrozenInstanceError):
        request.message = "outra"  # type: ignore[misc]


def test_chat_event_defaults_to_empty_citations() -> None:
    event = ChatEvent(type=ChatEventType.TOKEN, content="resposta")

    assert event.citations == ()
    assert event.best_score is None


def test_ingestion_result_counts_add_up() -> None:
    result = IngestionResult(documents=1, chunks=2, embedded_chunks=1, skipped_chunks=1)

    assert result.chunks == result.embedded_chunks + result.skipped_chunks


def test_source_page_is_immutable() -> None:
    page = SourcePage(source="apostila.pdf", title="Apostila", page=1, text="conteúdo")

    with pytest.raises(FrozenInstanceError):
        page.page = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    ("source", "title"),
    [
        (
            "sma-desenvolvendo-os-cuidados-de-saude-mental-na-aps-random.pdf",
            "Desenvolvendo os Cuidados de Saúde Mental na APS",
        ),
        (
            "sma-o-sujeito-a-integralidade-e-saude-mental.pdf",
            "O sujeito, a Integralidade e a Saúde Mental",
        ),
        (
            "sma-saude-mental-na-atencao-primaria-random.pdf",
            "Saúde Mental na Atenção Primária",
        ),
        (
            "sma-u-1-ampliando-o-conceito-de-saude-mental-random.pdf",
            "Ampliando o Conceito de Saúde Mental",
        ),
        ("novo_documento.pdf", "Novo Documento"),
    ],
)
def test_document_title_resolves_known_documents_and_fallback(
    source: str,
    title: str,
) -> None:
    assert resolve_document_title(source) == title
