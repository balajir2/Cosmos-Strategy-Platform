import os

from openai import OpenAI

from .base import LLMProvider

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(LLMProvider):
    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        self.client = client or OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content
