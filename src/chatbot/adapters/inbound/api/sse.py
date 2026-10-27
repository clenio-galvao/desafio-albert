"""Serialização estável dos eventos Server-Sent Events."""

import json

from chatbot.application.models import ChatEvent, ChatEventType


def encode_chat_event(event: ChatEvent) -> str:
    payload: dict[str, object] = {}
    if event.content is not None:
        payload["content"] = event.content
    if event.type is ChatEventType.METADATA:
        payload["citations"] = [
            {
                "source": citation.source,
                "page": citation.page,
                "chunk_id": citation.chunk_id,
            }
            for citation in event.citations
        ]
    return encode_sse(event.type.value, payload)


def encode_error(message: str) -> str:
    return encode_sse("error", {"message": message})


def encode_sse(event: str, payload: dict[str, object]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"
