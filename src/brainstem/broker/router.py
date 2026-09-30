"""Rule-based backend selection with local preference and ordered fallback.

The router remains deliberately deterministic: a caller may prefer a local
backend, then use the configured order of reachable providers.
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
