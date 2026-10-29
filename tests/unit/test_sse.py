from chatbot.adapters.inbound.api.sse import encode_chat_event
from chatbot.application import ChatEvent, ChatEventType
from chatbot.domain import Citation


def test_sse_omits_retrieval_score() -> None:
    encoded = encode_chat_event(
        ChatEvent(
            type=ChatEventType.METADATA,
            citations=(
                Citation(
                    source="apostila.pdf",
                    title="Apostila",
                    page=3,
                    chunk_id="chunk",
                ),
            ),
            best_score=0.91,
        )
    )

    assert "best_score" not in encoded
    assert "0.91" not in encoded
    assert "chunk" in encoded
