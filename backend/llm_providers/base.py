import json
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Common interface every LLM provider adapter implements."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a system+user prompt to the provider and return its raw text response."""
        raise NotImplementedError


def parse_evaluation_json(response_text: str) -> dict:
    """Extracts the rating/critique/recommendations JSON object from a raw LLM
    response, tolerating ```json-fenced or plain ```-fenced code blocks."""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse evaluation JSON from response: {e}") from e
