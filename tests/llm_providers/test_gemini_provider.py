from unittest.mock import MagicMock

from llm_providers.gemini_provider import GeminiProvider


def test_gemini_provider_complete_returns_text_and_wires_prompts_correctly():
    fake_response = MagicMock()
    fake_response.text = "hello from gemini"
    fake_model = MagicMock()
    fake_model.generate_content.return_value = fake_response
    fake_factory = MagicMock(return_value=fake_model)

    provider = GeminiProvider(model_factory=fake_factory, model="gemini-1.5-pro")
    result = provider.complete("system prompt", "user prompt")

    assert result == "hello from gemini"
    fake_factory.assert_called_once_with("system prompt")
    fake_model.generate_content.assert_called_once_with("user prompt")
