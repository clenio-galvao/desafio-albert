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


_REFUSAL_MARKERS = (
    "nao encontrei informacao suficiente",
    "nao ha informacao suficiente",
    "as apostilas nao contem",
    "os trechos fornecidos nao",
)


def _normalize_text(value: str) -> str:
    """Remove caixa, acentos e espaços extras para comparar textos."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.split())


def _is_refusal(answer: str) -> bool:
    """Detecta as recusas padronizadas do chatbot."""
    return any(marker in answer for marker in _REFUSAL_MARKERS)


def _retrieved_expected_source(
    citations: tuple[ObservedCitation, ...],
    expected_title: str,
    expected_pages: tuple[int, ...],
) -> bool:
    """Confere se alguma citação observada aponta para o trecho esperado."""
    normalized_title = _normalize_text(expected_title)
    return any(
        _normalize_text(citation.title) == normalized_title
        and citation.page in expected_pages
        for citation in citations
    )


def _cites_expected_source(
    answer: str,
    expected_title: str,
    expected_pages: tuple[int, ...],
) -> bool:
    """Confere se a resposta menciona o título e ao menos uma página esperada."""
    return _normalize_text(expected_title) in answer and any(
        re.search(rf"\b{page}\b", answer) is not None for page in expected_pages
    )


def _concept_coverage(
    answer: str,
    required_concepts: tuple[tuple[str, ...], ...],
) -> float:
    """Fração dos grupos de conceitos em que ao menos um sinônimo aparece."""
    if not required_concepts:
        return 1.0
    matched = sum(
        any(_normalize_text(alternative) in answer for alternative in alternatives)
        for alternatives in required_concepts
    )
    return matched / len(required_concepts)


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
    normalized_answer = _normalize_text(answer)
    refusal_correct = _is_refusal(normalized_answer)

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

    retrieval_hit = _retrieved_expected_source(citations, expected_title, expected_pages)
    citation_present = _cites_expected_source(
        normalized_answer,
        expected_title,
        expected_pages,
    )
    concept_coverage = _concept_coverage(normalized_answer, required_concepts)
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
