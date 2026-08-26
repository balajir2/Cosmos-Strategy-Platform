from unittest.mock import MagicMock

from llm_providers.openai_provider import OpenAIProvider


def test_openai_provider_complete_passes_messages_through():
    fake_message = MagicMock()
    fake_message.content = "hello from gpt"
    fake_choice = MagicMock()
    fake_choice.message = fake_message
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    provider = OpenAIProvider(client=fake_client, model="gpt-4o")
    messages = [{"role": "user", "content": "user prompt"}]
    result = provider.complete("system prompt", messages)

    assert result == "hello from gpt"
    fake_client.chat.completions.create.assert_called_once_with(
        model="gpt-4o",
        messages=[{"role": "system", "content": "system prompt"}, {"role": "user", "content": "user prompt"}],
    )


def test_openai_provider_complete_passes_multi_turn_history():
    fake_message = MagicMock()
    fake_message.content = "follow-up response"
    fake_choice = MagicMock()
    fake_choice.message = fake_message
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    provider = OpenAIProvider(client=fake_client, model="gpt-4o")
    messages = [
        {"role": "user", "content": "first turn"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second turn"},
    ]
    result = provider.complete("system prompt", messages)

    assert result == "follow-up response"
    fake_client.chat.completions.create.assert_called_once_with(
        model="gpt-4o",
        messages=[{"role": "system", "content": "system prompt"}] + messages,
    )
