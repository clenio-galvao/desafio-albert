"""Schemas públicos e estritos da API."""

from pydantic import BaseModel, ConfigDict, Field


class ChatBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    message: str = Field(min_length=1, max_length=20000)
    model: str = Field(min_length=1, max_length=128)


class ModelsResponse(BaseModel):
    models: tuple[str, ...]


class HealthResponse(BaseModel):
    status: str
