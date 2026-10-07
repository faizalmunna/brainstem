import pytest

from brainstem.adapters.registry import provider_order
from brainstem.manifest import ModelConfig


def test_provider_order_honours_manifest_default_and_fallbacks():
    config = ModelConfig(default_provider="openai", local_fallback="ollama", fallback_providers=["anthropic", "ollama"])

    assert provider_order(config) == ["openai", "anthropic", "ollama"]
    assert provider_order(config, prefer_local=True) == ["ollama", "openai", "anthropic"]
    assert provider_order(config, provider="anthropic") == ["anthropic"]


def test_provider_order_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        provider_order(ModelConfig(), provider="not-a-provider")
