"""Token-efficient completion pipeline: cache, route, call, then cache.

It powers ``brainstem ask`` but is intentionally separate from deterministic
MCP repository tools, which do not need to proxy model calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..adapters.base import ModelBackend
from .budget import CompletionBudget, estimate_tokens
from .cache import RequestCache, cache_key
from .router import Router
from .usage import UsageLedger


@dataclass(frozen=True, slots=True)
class BrokerResult:
    text: str
    backend: str
    cache_hit: bool
    estimated_tokens: int
    input_tokens_estimated: int
    output_tokens_estimated: int
    max_output_tokens: int


class RequestBroker:
    def __init__(self, cache: RequestCache, router: Router, usage_ledger: UsageLedger | None = None) -> None:
        self.cache = cache
        self.router = router
        self.usage_ledger = usage_ledger

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        prefer_local: bool = False,
        use_cache: bool = True,
        budget: CompletionBudget | None = None,
    ) -> BrokerResult:
        backend: ModelBackend = self.router.choose(prefer_local=prefer_local)
        budget = budget or CompletionBudget()
        input_tokens = budget.enforce_input(prompt, system)
        key = cache_key(
            backend.name, system, prompt, request_options={"max_output_tokens": budget.max_output_tokens}
        )

        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                return self._result(cached, backend.name, True, input_tokens, budget.max_output_tokens)

        text = backend.complete(prompt, system=system, max_output_tokens=budget.max_output_tokens)
        if use_cache:
            self.cache.set(key, text, backend.name)
        return self._result(text, backend.name, False, input_tokens, budget.max_output_tokens)

    def _result(
        self, text: str, backend: str, cache_hit: bool, input_tokens: int, max_output_tokens: int
    ) -> BrokerResult:
        output_tokens = estimate_tokens(text)
        if self.usage_ledger is not None:
            self.usage_ledger.record(
                backend=backend,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_hit=cache_hit,
            )
        return BrokerResult(
            text=text,
            backend=backend,
            cache_hit=cache_hit,
            estimated_tokens=input_tokens + output_tokens,
            input_tokens_estimated=input_tokens,
            output_tokens_estimated=output_tokens,
            max_output_tokens=max_output_tokens,
        )
