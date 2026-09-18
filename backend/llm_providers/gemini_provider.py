import os

from google import genai
from google.genai import types

from .base import LLMProvider

DEFAULT_MODEL = "gemini-3.1-pro-preview"


class GeminiProvider(LLMProvider):
    """Calls Gemini via the Generative Language API using a billed API key
    (GEMINI_API_KEY), not Vertex AI/Application Default Credentials - lets
    usage be tracked and rate-limited independently of the rest of the GCP
    project's IAM-based billing."""

    def __init__(self, chat_factory=None, model: str = DEFAULT_MODEL):
        self.model = model
        if chat_factory is None:
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

            def chat_factory(system_prompt: str, history: list):
                return client.chats.create(
                    model=self.model,
                    config=types.GenerateContentConfig(system_instruction=system_prompt),
                    history=history,
                )

        self._chat_factory = chat_factory

    def complete(self, system_prompt: str, messages: list) -> str:
        history = []
        for m in messages[:-1]:
            role = "model" if m["role"] == "assistant" else "user"
            history.append({"role": role, "parts": [{"text": m["content"]}]})
        chat = self._chat_factory(system_prompt, history)
        response = chat.send_message(messages[-1]["content"])
        return response.text
