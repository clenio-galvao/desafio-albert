"""Metadados canônicos da base documental conhecida."""

from pathlib import Path

_KNOWN_TITLES = (
    (
        "desenvolvendo-os-cuidados-de-saude-mental-na-aps",
        "Desenvolvendo os Cuidados de Saúde Mental na APS",
    ),
    (
        "o-sujeito-a-integralidade-e-saude-mental",
        "O sujeito, a Integralidade e a Saúde Mental",
    ),
    (
        "saude-mental-na-atencao-primaria",
        "Saúde Mental na Atenção Primária",
    ),
    (
        "ampliando-o-conceito-de-saude-mental",
        "Ampliando o Conceito de Saúde Mental",
    ),
)


def resolve_document_title(source: str) -> str:
    """Resolve o título uma vez, na fronteira de entrada dos documentos."""
    normalized = source.casefold()
    for marker, title in _KNOWN_TITLES:
        if marker in normalized:
            return title

    stem = Path(source).stem.replace("_", " ").replace("-", " ")
    return " ".join(stem.split()).title()
