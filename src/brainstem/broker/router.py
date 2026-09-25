"""Rule-based backend selection -- lever #3 in the plan's token-savings
ranking: "Local-model routing... for cheap subtasks -- classification,
extraction, routing -- instead of cloud calls. This is the largest raw-
cost lever, not just token count."

V1's router is deliberately simple (prefer-local flag + ordered fallback
list), not a learned/ML router: the plan explicitly scopes intelligent
cost/quality/latency-aware routing as something to grow into once there's
real usage data to route on, not something to fake with V1 heuristics.
"""

from __future__ import annotations

from ..adapters.base import ModelBackend


class NoBackendAvailable(RuntimeError):
    pass


class Router:
    def __init__(self, backends: list[ModelBackend]) -> None:
        """`backends` in preference order for the non-local-preferring
        case (typically: configured default provider, then any others)."""
        self._backends = backends

    def choose(self, prefer_local: bool = False) -> ModelBackend:
        ordered = sorted(self._backends, key=lambda b: (not (prefer_local and self._is_local(b))))
        for backend in ordered:
            if backend.is_available():
                return backend
        raise NoBackendAvailable(
            "No configured ModelBackend is available. Checked: "
            + ", ".join(b.name for b in self._backends)
        )

    @staticmethod
    def _is_local(backend: ModelBackend) -> bool:
        return backend.name.startswith("ollama/")
