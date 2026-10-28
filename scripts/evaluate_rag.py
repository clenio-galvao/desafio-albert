"""Executa a avaliação real do RAG com consumo explícito e controlado."""

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from chatbot.evaluation import ObservedCitation, evaluate_answer


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    setup_questions: list[str]
    answerable: bool
    expected_title: str | None
    expected_pages: list[int]
    required_concepts: list[list[str]]
    minimum_concept_coverage: float = Field(ge=0, le=1)


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    cases: list[EvaluationCase]


def _events(response: httpx.Response) -> Iterator[tuple[str, dict[str, Any]]]:
    event_name = "message"
    data_lines: list[str] = []
    for line in response.iter_lines():
        if line:
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
            continue
        if data_lines:
            payload = json.loads("\n".join(data_lines))
            if not isinstance(payload, dict):
                raise ValueError("evento SSE deve conter um objeto JSON")
            yield event_name, payload
        event_name = "message"
        data_lines = []


def _ask(
    client: httpx.Client,
    *,
    session_id: str,
    question: str,
    model: str,
) -> tuple[str, tuple[ObservedCitation, ...]]:
    tokens: list[str] = []
    citations: list[ObservedCitation] = []
    with client.stream(
        "POST",
        "/v1/chat/stream",
        json={"session_id": session_id, "message": question, "model": model},
    ) as response:
        response.raise_for_status()
        for event, payload in _events(response):
            if event == "token" and isinstance(payload.get("content"), str):
                tokens.append(payload["content"])
            elif event == "metadata" and isinstance(payload.get("citations"), list):
                for item in payload["citations"]:
                    if (
                        isinstance(item, dict)
                        and isinstance(item.get("title"), str)
                        and isinstance(item.get("page"), int)
                    ):
                        citations.append(
                            ObservedCitation(title=item["title"], page=item["page"])
                        )
            elif event == "error":
                raise RuntimeError(str(payload.get("message", "falha no streaming")))
    return "".join(tokens).strip(), tuple(citations)


def _load_dataset(path: Path) -> EvaluationDataset:
    return EvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--model", default="azure/gpt-5-mini")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluation/rag_cases.json"),
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="confirma chamadas reais ao modelo e possível consumo de cota",
    )
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error("use --confirm-live para autorizar a avaliação com chamadas reais")

    dataset = _load_dataset(args.dataset)
    passed = 0
    with httpx.Client(base_url=args.base_url, timeout=90) as client:
        for case in dataset.cases:
            session_id = f"eval-{case.id}-{uuid4()}"
            for setup_question in case.setup_questions:
                _ask(
                    client,
                    session_id=session_id,
                    question=setup_question,
                    model=args.model,
                )
            answer, citations = _ask(
                client,
                session_id=session_id,
                question=case.question,
                model=args.model,
            )
            score = evaluate_answer(
                answer=answer,
                citations=citations,
                answerable=case.answerable,
                expected_title=case.expected_title,
                expected_pages=tuple(case.expected_pages),
                required_concepts=tuple(
                    tuple(alternatives) for alternatives in case.required_concepts
                ),
                minimum_concept_coverage=case.minimum_concept_coverage,
            )
            passed += score.passed
            status = "PASS" if score.passed else "FAIL"
            print(
                f"{status} {case.id}: retrieval={score.retrieval_hit} "
                f"citation={score.citation_present} "
                f"concepts={score.concept_coverage:.0%} "
                f"refusal={score.refusal_correct}"
            )

    total = len(dataset.cases)
    print(f"Resultado: {passed}/{total} casos aprovados")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
