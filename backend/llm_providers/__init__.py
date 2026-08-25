from .base import LLMProvider, parse_evaluation_json
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider

_PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


def get_provider_adapter(name: str) -> LLMProvider:
    try:
        provider_cls = _PROVIDERS[name]
    except KeyError:
        raise ValueError(f"Unknown LLM provider '{name}'. Must be one of {sorted(_PROVIDERS)}.")
    return provider_cls()
