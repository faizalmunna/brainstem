"""Construction of explicitly configured optional model-provider adapters.

The core package does not import cloud SDKs. This registry is the only place
that turns a reviewed provider name into an optional adapter, keeping provider
selection testable and ensuring the CLI honours ``brain.toml`` policy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ModelBackend
from .ollama import OllamaBackend

if TYPE_CHECKING:
    from ..manifest import ModelConfig


PROVIDERS = ("anthropic", "openai", "ollama")


def provider_order(config: "ModelConfig", *, provider: str = "auto", prefer_local: bool = False) -> list[str]:
    """Return de-duplicated policy order without importing any cloud SDK."""
    normalized = provider.strip().lower()
    if normalized != "auto" and normalized not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Choose: auto, {', '.join(PROVIDERS)}.")
    if normalized != "auto":
        return [normalized]
    candidates = [config.default_provider, *config.fallback_providers]
    if prefer_local:
        candidates.insert(0, config.local_fallback)
    ordered: list[str] = []
    for candidate in candidates:
        if candidate in PROVIDERS and candidate not in ordered:
            ordered.append(candidate)
    return ordered


def build_backends(
    config: "ModelConfig", *, provider: str = "auto", model: str | None = None, prefer_local: bool = False
) -> list[ModelBackend]:
    """Build only configured optional adapters, in the selected policy order."""
    backends: list[ModelBackend] = []
    selected = provider.strip().lower()
    for name in provider_order(config, provider=provider, prefer_local=prefer_local):
        selected_model = model if model and (selected == name or selected == "auto" and name == config.default_provider) else None
        if name == "ollama":
            backends.append(OllamaBackend(model=selected_model or config.local_model))
        elif name == "anthropic":
            try:
                from .anthropic_backend import AnthropicBackend
            except ImportError:
                continue
            backends.append(AnthropicBackend(model=selected_model or config.anthropic_model))
        elif name == "openai":
            try:
                from .openai_backend import OpenAIBackend
            except ImportError:
                continue
            backends.append(OpenAIBackend(model=selected_model or config.openai_model))
    return backends
