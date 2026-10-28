import pytest

from chatbot.application import (
    ChatEvent,
    ChatEventType,
    ChatRequest,
    IngestionResult,
    SourcePage,
    UnsupportedModelError,
)
from chatbot.application.document_titles import document_title
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
    assert document_title(source) == title
