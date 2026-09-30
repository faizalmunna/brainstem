"""Token-efficient completion pipeline: cache, route, call, then cache.

It powers ``brainstem ask`` but is intentionally separate from deterministic
MCP repository tools, which do not need to proxy model calls.
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
    # This is an intentionally portable estimate. The larger saving comes from
    # avoiding unnecessary context and duplicate calls; provider-specific usage
    # accounting belongs in an individual backend adapter.
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
