import pytest

from brainstem.adapters.base import ModelBackend
from brainstem.broker.broker import RequestBroker
from brainstem.broker.cache import RequestCache, cache_key
from brainstem.broker.router import NoBackendAvailable, Router


class FakeBackend(ModelBackend):
    def __init__(self, name: str, available: bool = True) -> None:
        self.name = name
        self._available = available
        self.calls = 0

    def is_available(self) -> bool:
        return self._available

    def complete(self, prompt: str, *, system: str | None = None, **kwargs) -> str:
        self.calls += 1
        return f"response to: {prompt}"


def test_cache_key_is_stable_and_input_sensitive():
    a = cache_key("model", "sys", "prompt")
    b = cache_key("model", "sys", "prompt")
    c = cache_key("model", "sys", "different prompt")
    assert a == b
    assert a != c


def test_cache_get_miss_then_hit(tmp_path):
    cache = RequestCache(tmp_path / "cache.db")
    key = cache_key("m", None, "hello")

    assert cache.get(key) is None
    cache.set(key, "world", "m")
    assert cache.get(key) == "world"
    assert cache.stats() == {"hits": 1, "misses": 1, "hit_rate_pct": 50}


def test_router_prefers_local_when_requested():
    local = FakeBackend("ollama/llama3.2")
    cloud = FakeBackend("anthropic/claude")
    router = Router([cloud, local])

    assert router.choose(prefer_local=True).name == "ollama/llama3.2"
    assert router.choose(prefer_local=False).name == "anthropic/claude"


def test_router_falls_back_when_preferred_unavailable():
    local = FakeBackend("ollama/llama3.2", available=False)
    cloud = FakeBackend("anthropic/claude", available=True)
    router = Router([cloud, local])

    assert router.choose(prefer_local=True).name == "anthropic/claude"


def test_router_raises_when_nothing_available():
    router = Router([FakeBackend("a", available=False), FakeBackend("b", available=False)])
    with pytest.raises(NoBackendAvailable):
        router.choose()


def test_broker_caches_across_calls(tmp_path):
    backend = FakeBackend("fake/model")
    cache = RequestCache(tmp_path / "cache.db")
    broker = RequestBroker(cache, Router([backend]))

    first = broker.complete("hi")
    second = broker.complete("hi")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.text == second.text == "response to: hi"
    assert backend.calls == 1  # second call served from cache, backend not hit again


def test_broker_no_cache_flag_always_calls_backend(tmp_path):
    backend = FakeBackend("fake/model")
    cache = RequestCache(tmp_path / "cache.db")
    broker = RequestBroker(cache, Router([backend]))

    broker.complete("hi", use_cache=False)
    broker.complete("hi", use_cache=False)

    assert backend.calls == 2
