"""ModelBackend over the real Anthropic SDK. Optional (`pip install
brainstem[providers]`) -- adapters/base.py's ModelBackend interface exists
precisely so core logic never imports this module directly; it's only
constructed by callers (the CLI's `ask` command, future broker consumers)
that specifically want this provider.
"""

from __future__ import annotations

import os
from typing import Any

from .base import ModelBackend

DEFAULT_MODEL = "claude-sonnet-4-5"


class AnthropicBackend(ModelBackend):
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.name = f"anthropic/{model}"
        self.model = model
        self._client = None

    def is_available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, prompt: str, *, system: str | None = None, **kwargs: Any) -> str:
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=kwargs.pop("max_tokens", 1024),
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
