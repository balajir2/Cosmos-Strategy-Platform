from unittest.mock import MagicMock

from llm_providers.anthropic_provider import AnthropicProvider


def test_anthropic_provider_complete_passes_messages_through():
    fake_block = MagicMock()
    fake_block.text = "hello from claude"
    fake_response = MagicMock()
    fake_response.content = [fake_block]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    provider = AnthropicProvider(client=fake_client, model="claude-sonnet-5")
    messages = [{"role": "user", "content": "user prompt"}]
    result = provider.complete("system prompt", messages)

    assert result == "hello from claude"
    fake_client.messages.create.assert_called_once_with(
        model="claude-sonnet-5",
        max_tokens=1000,
        system="system prompt",
        messages=messages,
    )


def test_anthropic_provider_complete_passes_multi_turn_history():
    fake_block = MagicMock()
    fake_block.text = "follow-up response"
    fake_response = MagicMock()
    fake_response.content = [fake_block]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    provider = AnthropicProvider(client=fake_client, model="claude-sonnet-5")
    messages = [
        {"role": "user", "content": "first turn"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second turn"},
    ]
    result = provider.complete("system prompt", messages)

    assert result == "follow-up response"
    fake_client.messages.create.assert_called_once_with(
        model="claude-sonnet-5",
        max_tokens=1000,
        system="system prompt",
        messages=messages,
    )
