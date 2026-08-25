import os

import vertexai
from vertexai.generative_models import GenerativeModel

from .base import LLMProvider

DEFAULT_MODEL = "gemini-1.5-pro"


class GeminiProvider(LLMProvider):
    """Calls Gemini via Vertex AI using the runtime's GCP service account
    (Application Default Credentials) - no API key is stored or required."""

    def __init__(self, model_factory=None, model: str = DEFAULT_MODEL):
        self.model = model
        if model_factory is None:
            vertexai.init(
                project=os.environ["GCP_PROJECT_ID"],
                location=os.environ.get("GCP_LOCATION", "us-central1"),
            )

            def model_factory(system_prompt: str):
                return GenerativeModel(self.model, system_instruction=system_prompt)

        self._model_factory = model_factory

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        model = self._model_factory(system_prompt)
        response = model.generate_content(user_prompt)
        return response.text
