"""Local-model ModelBackend, talking to Ollama's OpenAI-compatible endpoint.

It uses Ollama's REST API rather than bundling a model runtime, keeping local
model support optional and independent from repository retrieval.
"""

from __future__ import annotations

from typing import Any

import httpx

from .base import ModelBackend

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaBackend(ModelBackend):
    def __init__(self, model: str = "llama3.2", base_url: str = DEFAULT_BASE_URL) -> None:
        self.name = f"ollama/{model}"
        self.model = model
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        """Server reachable AND this specific model is actually pulled --
        checking only the former let a router pick Ollama and then fail
        the real call with a 404 for an unpulled model, which defeats the
        point of a pre-flight availability check."""
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=2.0)
            if resp.status_code != 200:
                return False
            names = {m["name"] for m in resp.json().get("models", [])}
            return self.model in names or f"{self.model}:latest" in names
        except httpx.HTTPError:
            return False

    def complete(self, prompt: str, *, system: str | None = None, **kwargs: Any) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = httpx.post(
            f"{self.base_url}/api/chat",
            json={"model": self.model, "messages": messages, "stream": False},
            timeout=kwargs.pop("timeout", 60.0),
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")
