import os

from openai import OpenAI

from .base import LLMProvider

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(LLMProvider):
    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        self.client = client or OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = model

    def complete(self, system_prompt: str, messages: list) -> str:
        full_messages = [{"role": "system", "content": system_prompt}] + list(messages)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
        )
        return response.choices[0].message.content
