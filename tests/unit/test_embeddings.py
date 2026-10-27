import httpx
import pytest
import respx

from chatbot.adapters.outbound.openai_compatible import OpenAIEmbeddingAdapter


def embedding_response(items: list[tuple[int, list[float]]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "object": "list",
            "data": [
                {"object": "embedding", "index": index, "embedding": vector}
                for index, vector in items
            ],
            "model": "cohere/embed-v4.0",
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        },
    )


def make_adapter(batch_size: int = 2) -> OpenAIEmbeddingAdapter:
    return OpenAIEmbeddingAdapter(
        base_url="https://gateway.test/v1",
        api_key="secret",
        model="cohere/embed-v4.0",
        batch_size=batch_size,
        max_retries=0,
    )


@respx.mock
async def test_embedding_adapter_batches_and_restores_provider_order() -> None:
    route = respx.post("https://gateway.test/v1/embeddings").mock(
        side_effect=[
            embedding_response([(1, [2.0]), (0, [1.0])]),
            embedding_response([(0, [3.0])]),
        ]
    )

    vectors = await make_adapter().embed(["um", "dois", "três"])

    assert vectors == [[1.0], [2.0], [3.0]]
    assert route.call_count == 2


@respx.mock
async def test_embedding_adapter_handles_empty_input_without_request() -> None:
    route = respx.post("https://gateway.test/v1/embeddings")

    assert await make_adapter().embed([]) == []
    assert not route.called


@respx.mock
async def test_embedding_adapter_rejects_incomplete_provider_response() -> None:
    respx.post("https://gateway.test/v1/embeddings").mock(
        return_value=embedding_response([(0, [1.0])])
    )

    with pytest.raises(RuntimeError, match="quantidade inesperada"):
        await make_adapter().embed(["um", "dois"])


def test_embedding_adapter_validates_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        make_adapter(batch_size=0)
