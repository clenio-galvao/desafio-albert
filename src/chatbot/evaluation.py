"""Métricas determinísticas para avaliações controladas do RAG."""

import re
import unicodedata
from dataclasses import dataclass
from typing import NamedTuple


class ObservedCitation(NamedTuple):
    """Fonte retornada pelo evento de metadados da API."""

    title: str
    page: int


@dataclass(frozen=True, slots=True)
class EvaluationScore:
    """Resultado explicável de um caso do dataset de avaliação."""

    retrieval_hit: bool
    citation_present: bool
    concept_coverage: float
    refusal_correct: bool
    passed: bool


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.split())


def evaluate_answer(
    *,
    answer: str,
    citations: tuple[ObservedCitation, ...],
    answerable: bool,
    expected_title: str | None = None,
    expected_pages: tuple[int, ...] = (),
    required_concepts: tuple[tuple[str, ...], ...] = (),
    minimum_concept_coverage: float = 0.5,
) -> EvaluationScore:
    """Avalia recuperação, citação, conceitos essenciais e recusa."""
    normalized_answer = _normalize(answer)
    refusal_markers = (
        "nao encontrei informacao suficiente",
        "nao ha informacao suficiente",
        "as apostilas nao contem",
        "os trechos fornecidos nao",
    )
    refusal_correct = any(marker in normalized_answer for marker in refusal_markers)

    if not answerable:
        return EvaluationScore(
            retrieval_hit=not citations,
            citation_present=False,
            concept_coverage=1.0,
            refusal_correct=refusal_correct,
            passed=refusal_correct,
        )

    if expected_title is None or not expected_pages:
        raise ValueError("casos respondíveis exigem título e páginas esperadas")
    if not 0 <= minimum_concept_coverage <= 1:
        raise ValueError("minimum_concept_coverage deve estar entre zero e um")

    normalized_title = _normalize(expected_title)
    retrieval_hit = any(
        _normalize(citation.title) == normalized_title
        and citation.page in expected_pages
        for citation in citations
    )
    citation_present = normalized_title in normalized_answer and any(
        re.search(rf"\b{page}\b", normalized_answer) is not None
        for page in expected_pages
    )
    matched_concepts = sum(
        any(_normalize(alternative) in normalized_answer for alternative in alternatives)
        for alternatives in required_concepts
    )
    concept_coverage = (
        matched_concepts / len(required_concepts) if required_concepts else 1.0
    )
    passed = (
        retrieval_hit
        and citation_present
        and concept_coverage >= minimum_concept_coverage
        and not refusal_correct
    )
    return EvaluationScore(
        retrieval_hit=retrieval_hit,
        citation_present=citation_present,
        concept_coverage=concept_coverage,
        refusal_correct=refusal_correct,
        passed=passed,
    )
