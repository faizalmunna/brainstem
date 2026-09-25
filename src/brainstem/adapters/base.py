"""Adapter interfaces that keep external dependencies outside the core.

V1 ships one concrete implementation per adapter (see ollama.py and
memory/store.py). Swapping in Graphiti, LanceDB, vLLM, E2B, etc. later means
writing a new class against these interfaces, not touching core logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ModelBackend(ABC):
    """A callable LLM, local or remote (Anthropic/OpenAI/Gemini/Ollama/...)."""

    name: str

    @abstractmethod
    def complete(self, prompt: str, *, system: str | None = None, **kwargs: Any) -> str:
        """Return a plain-text completion for `prompt`."""

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap, side-effect-free check for whether this backend can be reached."""


class VectorStore(ABC):
    """Embedding index used as a ranking fallback by the retrieval engine.

    Not required for the deterministic-first runtime:
    the retrieval engine works from the symbol/dependency graph alone. A
    VectorStore is an optional precision boost, e.g. a LanceDB-backed
    implementation, plugged in when an embedding model is configured.
    """

    @abstractmethod
    def upsert(self, doc_id: str, text: str, metadata: dict[str, Any]) -> None: ...

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[tuple[str, float, dict[str, Any]]]:
        """Return (doc_id, score, metadata) tuples, best match first."""


class GraphBackend(ABC):
    """Pluggable substrate for the memory graph (decisions/history/rules).

    V1's default is the embedded sqlite MemoryStore (memory/store.py), which
    satisfies this shape without implementing the full interface. A future
    Graphiti/Neo4j-backed implementation is a drop-in for larger, multi-repo
    or multi-user deployments.
    """

    @abstractmethod
    def add_fact(
        self, kind: str, title: str, body: str, tags: list[str] | None = None
    ) -> str:
        """Persist a fact, returning its id."""

    @abstractmethod
    def query_facts(self, query: str, kind: str | None = None, limit: int = 10) -> list[dict[str, Any]]: ...


class Sandbox(ABC):
    """Isolated execution for untrusted agent-generated code or proposed
    skills. Self-extension must pass sandboxing, tests, a security check, and
    human approval before registration. Not implemented in V1;
    E2B/Daytona are the intended adapter targets."""

    @abstractmethod
    def run(self, command: list[str], *, timeout_s: int = 60) -> tuple[int, str, str]:
        """Execute `command` in isolation, returning (exit_code, stdout, stderr)."""


class ToolProvider(ABC):
    """A source of callable tools an agent profile can be granted, gated by
    the permission model (READ/WRITE/EXECUTE/NETWORK/INSTALL/DATABASE/
    DEPLOY/DELETE/SECRET). MCP tool exposure (mcp_server.py) is the V1
    ToolProvider; this interface exists so non-MCP tool sources (e.g. a
    direct IDE integration) can be added without touching dispatch logic."""

    @abstractmethod
    def list_tools(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...
