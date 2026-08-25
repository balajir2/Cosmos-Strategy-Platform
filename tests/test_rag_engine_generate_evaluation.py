from unittest.mock import MagicMock, patch

from rag_engine import RagEngine


def _make_engine():
    with patch.object(RagEngine, "__init__", lambda self: None):
        return RagEngine()


@patch("rag_engine.get_provider_adapter")
@patch("rag_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_generate_evaluation_uses_active_provider(mock_get_active, mock_get_adapter):
    fake_provider = MagicMock()
    fake_provider.complete.return_value = (
        '{"rating": "Level 3", "critique": "deep", "recommendations": "keep going"}'
    )
    mock_get_adapter.return_value = fake_provider

    engine = _make_engine()
    result = engine.generate_evaluation("Q?", "my answer", [])

    assert result == {"rating": "Level 3", "critique": "deep", "recommendations": "keep going"}
    mock_get_adapter.assert_called_once_with("anthropic")


@patch("rag_engine.get_provider_adapter")
@patch("rag_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_generate_evaluation_falls_back_on_provider_error(mock_get_active, mock_get_adapter):
    fake_provider = MagicMock()
    fake_provider.complete.side_effect = RuntimeError("provider is down")
    mock_get_adapter.return_value = fake_provider

    engine = _make_engine()
    result = engine.generate_evaluation("Q?", "short", [])

    assert "rating" in result and "critique" in result and "recommendations" in result
