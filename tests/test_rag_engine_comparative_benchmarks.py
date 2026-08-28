from unittest.mock import MagicMock, patch

from rag_engine import RagEngine


def _make_engine():
    with patch.object(RagEngine, "__init__", lambda self: None):
        return RagEngine()


@patch("rag_engine.get_provider_adapter")
@patch("rag_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_generate_comparative_benchmarks_uses_active_provider(mock_get_active, mock_get_adapter):
    fake_provider = MagicMock()
    fake_provider.complete.return_value = (
        '{"level_1": "surface fact", "level_2": "customer need", "level_3": "deep insight"}'
    )
    mock_get_adapter.return_value = fake_provider

    engine = _make_engine()
    result = engine.generate_comparative_benchmarks(
        "Q?", "my answer",
        [{"source": "framework", "source_file": "deck.pdf", "text": "framework context"}],
    )

    assert result == {"level_1": "surface fact", "level_2": "customer need", "level_3": "deep insight"}
    mock_get_adapter.assert_called_once_with("anthropic")


@patch("rag_engine.get_provider_adapter")
@patch("rag_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_generate_comparative_benchmarks_does_not_grade_the_users_answer(mock_get_active, mock_get_adapter):
    fake_provider = MagicMock()
    fake_provider.complete.return_value = '{"level_1": "a", "level_2": "b", "level_3": "c"}'
    mock_get_adapter.return_value = fake_provider

    engine = _make_engine()
    engine.generate_comparative_benchmarks("Q?", "my answer", [])

    system_prompt = fake_provider.complete.call_args[0][0]
    assert "level_1" in system_prompt and "level_2" in system_prompt and "level_3" in system_prompt


@patch("rag_engine.get_provider_adapter")
@patch("rag_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_generate_comparative_benchmarks_falls_back_on_provider_error(mock_get_active, mock_get_adapter):
    fake_provider = MagicMock()
    fake_provider.complete.side_effect = RuntimeError("provider is down")
    mock_get_adapter.return_value = fake_provider

    engine = _make_engine()
    result = engine.generate_comparative_benchmarks("Q?", "short", [])

    assert set(result.keys()) == {"level_1", "level_2", "level_3"}


def test_fallback_local_benchmarks_returns_all_three_levels():
    engine = _make_engine()
    result = engine.fallback_local_benchmarks()
    assert set(result.keys()) == {"level_1", "level_2", "level_3"}
    assert all(isinstance(v, str) and v for v in result.values())
