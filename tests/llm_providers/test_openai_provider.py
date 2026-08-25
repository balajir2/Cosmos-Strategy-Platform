from unittest.mock import MagicMock

from llm_providers.openai_provider import OpenAIProvider


def test_openai_provider_complete_returns_text_and_calls_sdk_correctly():
    fake_message = MagicMock()
    fake_message.content = "hello from gpt"
    fake_choice = MagicMock()
    fake_choice.message = fake_message
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    provider = OpenAIProvider(client=fake_client, model="gpt-4o")
    result = provider.complete("system prompt", "user prompt")

    assert result == "hello from gpt"
    fake_client.chat.completions.create.assert_called_once_with(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ],
    )
