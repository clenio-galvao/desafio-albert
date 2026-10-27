"""Títulos legíveis para os documentos fixos da base de conhecimento."""

from pathlib import Path

_KNOWN_TITLES = (
    (
        "desenvolvendo-os-cuidados-de-saude-mental-na-aps",
        "Desenvolvendo os Cuidados de Saúde Mental na APS",
    ),
    (
        "o-sujeito-a-integralidade-e-saude-mental",
        "O Sujeito, a Integralidade e a Saúde Mental",
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


def document_title(source: str) -> str:
    """Resolve títulos canônicos e oferece fallback para novos documentos."""
    normalized = source.casefold()
    for marker, title in _KNOWN_TITLES:
        if marker in normalized:
            return title

    stem = Path(source).stem.replace("_", " ").replace("-", " ")
    return " ".join(stem.split()).title()
