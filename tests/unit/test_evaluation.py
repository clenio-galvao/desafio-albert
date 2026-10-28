import pytest

from chatbot.evaluation import ObservedCitation, evaluate_answer


def test_evaluation_accepts_grounded_answer_with_normalized_text() -> None:
    score = evaluate_answer(
        answer=(
            "É uma estratégia de comunicação que favorece a compreensão. "
            "[O sujeito, a Integralidade e a Saúde Mental, p. 29]"
        ),
        citations=(
            ObservedCitation(
                title="O sujeito, a Integralidade e a Saúde Mental",
                page=29,
            ),
        ),
        answerable=True,
        expected_title="O sujeito, a Integralidade e a Saúde Mental",
        expected_pages=(29,),
        required_concepts=(
            ("comunicacao",),
            ("compreensão", "entendimento"),
        ),
        minimum_concept_coverage=1,
    )

    assert score.retrieval_hit is True
    assert score.citation_present is True
    assert score.concept_coverage == 1
    assert score.refusal_correct is False
    assert score.passed is True


def test_evaluation_reports_each_grounding_failure() -> None:
    score = evaluate_answer(
        answer="Não há informação suficiente para responder.",
        citations=(ObservedCitation(title="Outro documento", page=1),),
        answerable=True,
        expected_title="Documento esperado",
        expected_pages=(2,),
        required_concepts=(("conceito ausente",),),
    )

    assert score.retrieval_hit is False
    assert score.citation_present is False
    assert score.concept_coverage == 0
    assert score.refusal_correct is True
    assert score.passed is False


@pytest.mark.parametrize(
    ("answer", "citations", "passed", "retrieval_hit"),
    [
        ("As apostilas não contêm essa informação.", (), True, True),
        (
            "Resposta inventada.",
            (ObservedCitation(title="Documento", page=1),),
            False,
            False,
        ),
    ],
)
def test_evaluation_scores_refusal_cases(
    answer: str,
    citations: tuple[ObservedCitation, ...],
    passed: bool,
    retrieval_hit: bool,
) -> None:
    score = evaluate_answer(
        answer=answer,
        citations=citations,
        answerable=False,
    )

    assert score.passed is passed
    assert score.refusal_correct is passed
    assert score.retrieval_hit is retrieval_hit
    assert score.citation_present is False
    assert score.concept_coverage == 1


@pytest.mark.parametrize(
    "options",
    [
        {"expected_title": None, "expected_pages": (1,)},
        {"expected_title": "Documento", "expected_pages": ()},
    ],
)
def test_answerable_evaluation_requires_expected_source(
    options: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="título e páginas"):
        evaluate_answer(
            answer="resposta",
            citations=(),
            answerable=True,
            **options,  # type: ignore[arg-type]
        )


def test_evaluation_validates_concept_threshold() -> None:
    with pytest.raises(ValueError, match="entre zero e um"):
        evaluate_answer(
            answer="resposta",
            citations=(),
            answerable=True,
            expected_title="Documento",
            expected_pages=(1,),
            minimum_concept_coverage=1.1,
        )
