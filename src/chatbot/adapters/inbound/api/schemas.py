"""Schemas públicos e estritos da API."""

from pydantic import BaseModel, ConfigDict, Field


class ChatBody(BaseModel):
    """Corpo estrito do chat: rejeita campos extras e limita o identificador da sessão."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    message: str = Field(min_length=1, max_length=20000)
    model: str = Field(min_length=1, max_length=128)


class ModelsResponse(BaseModel):
    """Lista pública dos modelos aceitos pela API."""

    models: tuple[str, ...]


class HealthResponse(BaseModel):
    """Estado de liveness ou readiness sem detalhes internos."""

    status: str
