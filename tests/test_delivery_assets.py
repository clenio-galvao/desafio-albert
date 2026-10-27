import json
from pathlib import Path


def test_postman_collection_is_valid_and_contains_streaming_request() -> None:
    path = Path("docs/postman/chatbot-rag.postman_collection.json")

    collection = json.loads(path.read_text(encoding="utf-8"))

    assert collection["info"]["name"] == "Desafio Albert — Chatbot RAG"
    chat_requests = collection["item"][1]["item"]
    streaming = next(item for item in chat_requests if item["name"] == "Streaming SSE")
    assert streaming["request"]["method"] == "POST"
    assert streaming["request"]["url"] == "{{baseUrl}}/v1/chat/stream"
    assert "api_key" not in json.dumps(collection).lower()
