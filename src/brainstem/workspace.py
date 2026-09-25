"""Wires manifest + graph + memory + skills into one handle for a target
repo. Shared by the CLI and the MCP server so both talk to the same state.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from .indexer.graph import RepoGraph, load_graph
from .manifest import BrainManifest, brain_dir, load_manifest
from .memory.store import MemoryStore
from .skills.registry import SkillRegistry
from .skills.state import SkillState, state_path

GRAPH_FILENAME = "index/graph.json"
MEMORY_FILENAME = "memory/facts.db"
VECTOR_DIRNAME = "index/vectors.lance"


def _bundled_skills_dir() -> Path:
    """Bundled skills live at `src/brainstem/skills_bundled/` -- inside the
    actual Python package, not a sibling directory -- specifically so they
    install as real package data and resolve correctly regardless of how
    brainstem was installed (editable dev checkout, a built wheel, or the
    npm wrapper's private venv, where the old sibling-directory path
    assumption silently resolved to nothing and every skill list came back
    empty). `importlib.resources` is the portable way to locate this: it
    works the same whether the package is a loose directory on disk or
    zipped inside a wheel."""
    return Path(str(importlib.resources.files("brainstem") / "skills_bundled"))


class Workspace:
    def __init__(self, repo_root: Path, manifest: BrainManifest) -> None:
        self.repo_root = repo_root
        self.manifest = manifest
        self._graph: RepoGraph | None = None
        self._memory: MemoryStore | None = None
        self._skills: SkillRegistry | None = None
        self._vector_store_loaded = False
        self._vector_store = None

    @classmethod
    def open(cls, repo_root: Path) -> "Workspace":
        repo_root = repo_root.resolve()
        manifest = load_manifest(repo_root)
        return cls(repo_root, manifest)

    @property
    def graph(self) -> RepoGraph | None:
        if self._graph is None:
            self._graph = load_graph(brain_dir(self.repo_root) / GRAPH_FILENAME)
        return self._graph

    @property
    def memory(self) -> MemoryStore:
        if self._memory is None:
            self._memory = MemoryStore(brain_dir(self.repo_root) / MEMORY_FILENAME)
        return self._memory

    @property
    def skills(self) -> SkillRegistry:
        """Bundled packs + everything under `<repo>/.brain/skills/` --
        which includes both hand-authored repo-local skills and anything
        installed via `brainstem skill install` (which lands in
        `.brain/skills/installed/<pack>/`, discovered here automatically,
        no separate wiring needed). Enable/disable state is loaded from
        `.brain/skills/state.json` (skills/state.py)."""
        if self._skills is None:
            state = SkillState(state_path(self.repo_root))
            self._skills = SkillRegistry(
                [_bundled_skills_dir(), brain_dir(self.repo_root) / "skills"],
                state=state,
            )
        return self._skills

    @property
    def vector_store(self):
        """Return the optional semantic-retrieval backend when available.

        Returns ``None`` when the ``vector`` extra is absent or no embedded
        index exists. Deterministic retrieval remains available in both cases.
        """
        if not self._vector_store_loaded:
            self._vector_store_loaded = True
            vector_dir = brain_dir(self.repo_root) / VECTOR_DIRNAME
            if vector_dir.exists():
                try:
                    from .adapters.lancedb_store import LanceDBVectorStore

                    self._vector_store = LanceDBVectorStore(vector_dir)
                except ImportError:
                    self._vector_store = None
        return self._vector_store

    def close(self) -> None:
        """Release the sqlite handle if the memory store was opened.
        Not required for short-lived CLI commands (the process exit
        reclaims it), but `serve` is a long-lived process and callers
        that open a Workspace in a loop/test (performance testing hit this
        directly on Windows, where an open sqlite handle blocks deleting
        its containing directory) should call this explicitly."""
        if self._memory is not None:
            self._memory.close()
            self._memory = None
