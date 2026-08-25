from .base import LLMProvider, parse_evaluation_json
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider

_PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


_adapter_cache: dict = {}


def get_provider_adapter(name: str) -> LLMProvider:
    try:
        provider_cls = _PROVIDERS[name]
    except KeyError:
        raise ValueError(f"Unknown LLM provider '{name}'. Must be one of {sorted(_PROVIDERS)}.")

    if name not in _adapter_cache:
        _adapter_cache[name] = provider_cls()

    return _adapter_cache[name]
