"""Portable completion-budget policy.

Providers expose different tokenizers and usage fields.  This module makes the
control-plane decision before a request leaves the machine, using a deliberately
conservative, documented character estimate.  Provider adapters still receive a
real output cap; the estimate is never presented as billing-grade accounting.
"""

from __future__ import annotations

from dataclasses import dataclass


CHARS_PER_TOKEN_ESTIMATE = 4


class TokenBudgetExceeded(ValueError):
    """Raised before an oversized prompt is sent to a model provider."""


def estimate_tokens(*texts: str | None) -> int:
    """Return a portable, conservative-enough token estimate for policy use."""
    return sum(len(text or "") for text in texts) // CHARS_PER_TOKEN_ESTIMATE


@dataclass(frozen=True, slots=True)
class CompletionBudget:
    """Limits applied to one completion request.

    ``max_output_tokens`` is passed to the selected provider adapter.  Input
    enforcement happens locally before the provider is contacted, so an
    accidentally enormous task packet cannot silently become a costly call.
    """

    max_input_tokens: int = 16_000
    max_output_tokens: int = 1_024

    def __post_init__(self) -> None:
        if not 1 <= self.max_input_tokens <= 1_000_000:
            raise ValueError("max_input_tokens must be between 1 and 1000000.")
        if not 1 <= self.max_output_tokens <= 100_000:
            raise ValueError("max_output_tokens must be between 1 and 100000.")

    def input_tokens(self, prompt: str, system: str | None = None) -> int:
        return estimate_tokens(system, prompt)

    def enforce_input(self, prompt: str, system: str | None = None) -> int:
        estimated = self.input_tokens(prompt, system)
        if estimated > self.max_input_tokens:
            raise TokenBudgetExceeded(
                "Estimated input is "
                f"{estimated} tokens, above the configured {self.max_input_tokens}-token input budget. "
                "Reduce the task packet or raise --max-input-tokens deliberately."
            )
        return estimated
