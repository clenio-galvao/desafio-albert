"""Adapters para o gateway no formato da API OpenAI."""

from chatbot.adapters.outbound.openai_compatible.chat import OpenAIChatAdapter
from chatbot.adapters.outbound.openai_compatible.embeddings import OpenAIEmbeddingAdapter

__all__ = ["OpenAIChatAdapter", "OpenAIEmbeddingAdapter"]
