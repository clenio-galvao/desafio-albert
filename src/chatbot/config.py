"""Configuração validada e carregada exclusivamente do ambiente."""

from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração da aplicação sem valores secretos no código."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    log_level: str = "INFO"
    openai_base_url: str
    openai_api_key: SecretStr
    chat_models: str = "azure/gpt-5-mini,azure/gpt-6-luna"
    embedding_model: str = "cohere/embed-v4.0"
    qdrant_url: str
    qdrant_api_key: SecretStr
    qdrant_collection: str = "mental-health-v1"
    documents_dir: Path = Path("data/documents")
    chunk_size_tokens: int = Field(default=700, ge=50)
    chunk_overlap_tokens: int = Field(default=100, ge=0)
    embedding_batch_size: int = Field(default=32, ge=1, le=128)
    retrieval_top_k: int = Field(default=3, ge=1, le=20)
    retrieval_score_threshold: float = Field(default=0.35, ge=0, le=1)
    retrieval_following_pages: int = Field(default=1, ge=0, le=2)
    session_ttl_seconds: int = Field(default=3600, ge=60)
    session_max_messages: int = Field(default=12, ge=2, le=50)
    session_max_count: int = Field(default=10_000, ge=1)
    retrieval_history_messages: int = Field(default=4, ge=0, le=20)
    max_message_length: int = Field(default=4000, ge=100, le=20000)
    max_concurrent_streams: int = Field(default=32, ge=1, le=1000)
    stream_timeout_seconds: float = Field(default=60.0, ge=0, le=300)
    cors_origins: str = ""

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> "Settings":
        """Impede sobreposição maior ou igual ao tamanho do chunk."""
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("chunk_overlap_tokens deve ser menor que chunk_size_tokens")
        return self

    @property
    def allowed_chat_models(self) -> tuple[str, ...]:
        """Normaliza e deduplica a allowlist configurada em `chat_models`."""
        models = tuple(model.strip() for model in self.chat_models.split(",") if model.strip())
        if not models:
            raise ValueError("chat_models deve conter ao menos um modelo")
        return tuple(dict.fromkeys(models))

    @property
    def allowed_cors_origins(self) -> tuple[str, ...]:
        """Origens explícitas de CORS; vazio deixa o middleware desligado."""
        return tuple(
            dict.fromkeys(
                origin.strip()
                for origin in self.cors_origins.split(",")
                if origin.strip()
            )
        )
