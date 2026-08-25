from unittest.mock import patch

import pytest

from llm_providers import get_provider_adapter
from llm_providers.anthropic_provider import AnthropicProvider
from llm_providers.openai_provider import OpenAIProvider
from llm_providers.gemini_provider import GeminiProvider


def test_get_provider_adapter_rejects_unknown_name():
    with pytest.raises(ValueError):
        get_provider_adapter("cohere")


def test_get_provider_adapter_returns_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("llm_providers.anthropic_provider.Anthropic"):
        provider = get_provider_adapter("anthropic")
    assert isinstance(provider, AnthropicProvider)


def test_get_provider_adapter_returns_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("llm_providers.openai_provider.OpenAI"):
        provider = get_provider_adapter("openai")
    assert isinstance(provider, OpenAIProvider)


def test_get_provider_adapter_returns_gemini(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    with patch("llm_providers.gemini_provider.vertexai"), patch(
        "llm_providers.gemini_provider.GenerativeModel"
    ):
        provider = get_provider_adapter("gemini")
    assert isinstance(provider, GeminiProvider)
