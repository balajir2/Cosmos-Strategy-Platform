from unittest.mock import MagicMock

from llm_providers.gemini_provider import GeminiProvider


def test_gemini_provider_complete_single_turn():
    fake_response = MagicMock()
    fake_response.text = "hello from gemini"
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = fake_response
    fake_model = MagicMock()
    fake_model.start_chat.return_value = fake_chat
    fake_factory = MagicMock(return_value=fake_model)

    provider = GeminiProvider(model_factory=fake_factory, model="gemini-1.5-pro")
    messages = [{"role": "user", "content": "user prompt"}]
    result = provider.complete("system prompt", messages)

    assert result == "hello from gemini"
    fake_factory.assert_called_once_with("system prompt")
    fake_model.start_chat.assert_called_once_with(history=[])
    fake_chat.send_message.assert_called_once_with("user prompt")


def test_gemini_provider_complete_multi_turn_builds_history():
    fake_response = MagicMock()
    fake_response.text = "follow-up response"
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = fake_response
    fake_model = MagicMock()
    fake_model.start_chat.return_value = fake_chat
    fake_factory = MagicMock(return_value=fake_model)

    provider = GeminiProvider(model_factory=fake_factory, model="gemini-1.5-pro")
    messages = [
        {"role": "user", "content": "first turn"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second turn"},
    ]
    result = provider.complete("system prompt", messages)

    assert result == "follow-up response"
    fake_model.start_chat.assert_called_once_with(history=[
        {"role": "user", "parts": ["first turn"]},
        {"role": "model", "parts": ["first reply"]},
    ])
    fake_chat.send_message.assert_called_once_with("second turn")
