import pytest

from chatbot.application import (
    ChatEvent,
    ChatEventType,
    ChatRequest,
    IngestionResult,
    SourcePage,
    UnsupportedModelError,
)
from chatbot.application.use_cases import ModelCatalog


def test_model_catalog_normalizes_deduplicates_and_lists_models() -> None:
    catalog = ModelCatalog([" model-a ", "model-b", "model-a", " "])

    assert catalog.execute() == ("model-a", "model-b")
    catalog.ensure_supported("model-b")


def test_model_catalog_rejects_empty_configuration() -> None:
    with pytest.raises(ValueError, match="ao menos um"):
        ModelCatalog([" ", ""])


def test_model_catalog_rejects_unsupported_model() -> None:
    catalog = ModelCatalog(["model-a"])

    with pytest.raises(UnsupportedModelError, match="model-b"):
        catalog.ensure_supported("model-b")


def test_application_data_contracts_are_immutable_values() -> None:
    request = ChatRequest(session_id="session", message="pergunta", model="model-a")
    event = ChatEvent(type=ChatEventType.TOKEN, content="resposta")
    page = SourcePage(source="apostila.pdf", page=1, text="conteúdo")
    result = IngestionResult(documents=1, chunks=2, embedded_chunks=1, skipped_chunks=1)

    assert request.model == "model-a"
    assert event.citations == ()
    assert page.page == 1
    assert result.chunks == result.embedded_chunks + result.skipped_chunks
