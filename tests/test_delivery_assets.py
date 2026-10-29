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


def test_env_example_keeps_cors_disabled_until_an_explicit_origin() -> None:
    example = Path(".env.example").read_text(encoding="utf-8")

    assert "\nCORS_ORIGINS=\n" in example or example.endswith("CORS_ORIGINS=\n")
    assert "CORS_ORIGINS=*" not in example
    assert "http://localhost:5173" in example


def test_evaluation_and_load_scripts_exist() -> None:
    assert Path("scripts/evaluate_rag.py").is_file()
    assert Path("scripts/load_test.py").is_file()


def test_documentation_links_architecture_decisions_and_demo_guide() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    adr_index = Path("docs/adr/README.md").read_text(encoding="utf-8")

    assert "[docs/adr](docs/adr/README.md)" in readme
    assert "[docs/DEMO.md](docs/DEMO.md)" in readme
    assert ".cursor/rules/clean-code-python.mdc" in readme
    assert ".cursor/rules/nomenclatura.mdc" in readme
    assert ".cursor/rules/pytest-um-comportamento.mdc" in readme
    for rule in (
        "clean-code-python.mdc",
        "nomenclatura.mdc",
        "pytest-um-comportamento.mdc",
    ):
        assert Path(".cursor/rules", rule).is_file()
    assert "Uso de IA no desenvolvimento" in readme
    assert "python scripts/load_test.py" in readme
    assert "Troubleshooting" in Path("docs/DEMO.md").read_text(encoding="utf-8")
    for number in range(1, 7):
        filename = next(Path("docs/adr").glob(f"{number:04d}-*.md"))
        assert filename.name in adr_index


def test_deployment_files_use_non_root_user_and_external_secrets() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    blueprint = Path("render.yaml").read_text(encoding="utf-8")
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    assert "USER chatbot" in dockerfile
    assert "${PORT:-8000}" in dockerfile
    assert "healthCheckPath: /health/ready" in blueprint
    assert "autoDeployTrigger: checksPass" in blueprint
    assert "CORS_ORIGINS" in blueprint
    assert blueprint.count("sync: false") == 7
    assert "replace-me" not in blueprint
    assert ".env" in dockerignore
    assert "data" in dockerignore
