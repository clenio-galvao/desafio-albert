import pytest
from pydantic import ValidationError

from chatbot.config import Settings


def make_settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "openai_base_url": "https://gateway.test/v1",
        "openai_api_key": "secret",
        "qdrant_url": "https://qdrant.test",
        "qdrant_api_key": "secret",
    }
    values.update(changes)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_settings_parse_and_deduplicate_models() -> None:
    settings = make_settings(
        chat_models=" model-a,model-b,model-a ",
        cors_origins=" https://app.test,https://admin.test,https://app.test ",
    )

    assert settings.allowed_chat_models == ("model-a", "model-b")
    assert settings.allowed_cors_origins == (
        "https://app.test",
        "https://admin.test",
    )


def test_settings_keep_secret_values_out_of_plain_fields() -> None:
    settings = make_settings()

    assert settings.openai_api_key.get_secret_value() == "secret"


def test_settings_default_retrieval_values() -> None:
    settings = make_settings()

    assert settings.retrieval_top_k == 3
    assert settings.retrieval_score_threshold == 0.35
    assert settings.retrieval_following_pages == 1


def test_settings_reject_empty_model_list() -> None:
    settings = make_settings(chat_models=" , ")

    with pytest.raises(ValueError, match="chat_models"):
        _ = settings.allowed_chat_models


def test_settings_reject_invalid_chunk_overlap() -> None:
    with pytest.raises(ValidationError, match="chunk_overlap_tokens"):
        make_settings(chunk_size_tokens=100, chunk_overlap_tokens=100)
