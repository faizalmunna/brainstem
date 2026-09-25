"""The token-efficiency pipeline itself: cache -> route -> call -> cache.

This exists as infrastructure for brainstem's own future needs (V2 self-
extension checks, e.g.) and as a directly usable utility (`brainstem ask`)
today -- it is deliberately *not* wired into the Q8 MCP tool surface,
because those tools answer deterministic repo questions and don't need an
LLM call at all; conflating "the brain answers a question" with "the brain
also proxies model calls" would blur exactly the boundary the plan's
retrieval design is built to avoid crossing unnecessarily.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..adapters.base import ModelBackend
from .cache import RequestCache, cache_key
from .router import Router


@dataclass(frozen=True, slots=True)
class BrokerResult:
    text: str
    backend: str
    cache_hit: bool
    estimated_tokens: int


def _estimate_tokens(*texts: str) -> int:
    # Deliberately crude (chars // 4): the plan's own token-savings ranking
    # puts real leverage in *not sending* tokens (cache/routing/retrieval),
    # not in precisely counting the ones that are sent. A provider-exact
    # count (from response usage fields) is a natural upgrade once a
    # specific backend's response shape is being parsed for more than text.
    return sum(len(t) for t in texts) // 4


class RequestBroker:
    def __init__(self, cache: RequestCache, router: Router) -> None:
        self.cache = cache
        self.router = router

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        prefer_local: bool = False,
        use_cache: bool = True,
    ) -> BrokerResult:
        backend: ModelBackend = self.router.choose(prefer_local=prefer_local)
        key = cache_key(backend.name, system, prompt)

        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                return BrokerResult(
                    text=cached, backend=backend.name, cache_hit=True, estimated_tokens=_estimate_tokens(prompt, cached)
                )

        text = backend.complete(prompt, system=system)
        if use_cache:
            self.cache.set(key, text, backend.name)
        return BrokerResult(
            text=text, backend=backend.name, cache_hit=False, estimated_tokens=_estimate_tokens(prompt, text)
        )
