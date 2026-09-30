"""ModelBackend over the real OpenAI SDK. Optional (`pip install
brainstem[providers]`) -- see anthropic_backend.py's module docstring for
why this isn't imported by core logic directly.
"""

from __future__ import annotations

import os
from typing import Any

from .base import ModelBackend

DEFAULT_MODEL = "gpt-4.1-mini"


class OpenAIBackend(ModelBackend):
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.name = f"openai/{model}"
        self.model = model
        self._client = None

    def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def _get_client(self):
        if self._client is None:
            import openai

            self._client = openai.OpenAI()
        return self._client

    def complete(self, prompt: str, *, system: str | None = None, **kwargs: Any) -> str:
        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(model=self.model, messages=messages, **kwargs)
        return response.choices[0].message.content or ""
