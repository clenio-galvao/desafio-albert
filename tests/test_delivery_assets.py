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


def test_rag_evaluation_dataset_covers_core_scenarios() -> None:
    path = Path("evaluation/rag_cases.json")
    dataset = json.loads(path.read_text(encoding="utf-8"))

    assert dataset["version"] == 1
    cases = dataset["cases"]
    identifiers = {case["id"] for case in cases}
    assert {
        "escuta-terapeutica",
        "escuta-terapeutica-multiturno",
        "ferramentas-pratica-clinica",
        "recusa-fora-do-escopo",
    } <= identifiers
    assert any(case["setup_questions"] for case in cases)
    assert any(not case["answerable"] for case in cases)
    assert all(
        case["expected_title"] and case["expected_pages"]
        for case in cases
        if case["answerable"]
    )
    assert Path("scripts/evaluate_rag.py").is_file()
