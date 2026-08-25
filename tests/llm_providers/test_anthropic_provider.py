from unittest.mock import MagicMock

from llm_providers.anthropic_provider import AnthropicProvider


def test_anthropic_provider_complete_returns_text_and_calls_sdk_correctly():
    fake_block = MagicMock()
    fake_block.text = "hello from claude"
    fake_response = MagicMock()
    fake_response.content = [fake_block]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    provider = AnthropicProvider(client=fake_client, model="claude-sonnet-5")
    result = provider.complete("system prompt", "user prompt")

    assert result == "hello from claude"
    fake_client.messages.create.assert_called_once_with(
        model="claude-sonnet-5",
        max_tokens=1000,
        system="system prompt",
        messages=[{"role": "user", "content": "user prompt"}],
    )
