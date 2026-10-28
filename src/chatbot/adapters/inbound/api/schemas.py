"""Schemas públicos e estritos da API."""

from pydantic import BaseModel, ConfigDict, Field

from chatbot.config import DEFAULT_MAX_MESSAGE_LENGTH


class ChatBody(BaseModel):
    """Corpo estrito do chat: rejeita campos extras e limita o identificador da sessão.

    O teto de `message` é o mesmo default de `Settings.max_message_length`.
    A aplicação ainda pode recusar um valor menor se o ambiente configurar
    um limite mais baixo.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    message: str = Field(min_length=1, max_length=DEFAULT_MAX_MESSAGE_LENGTH)
    model: str = Field(min_length=1, max_length=128)


class ModelsResponse(BaseModel):
    """Lista pública dos modelos aceitos pela API."""

    models: tuple[str, ...]


class HealthResponse(BaseModel):
    """Estado de liveness ou readiness sem detalhes internos."""

    status: str
