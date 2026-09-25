"""Embedded memory store: decisions, bug/fix history, rules, and skill
usage -- the "Repository/Project Memory" and "Skill Memory" tiers from
the plan's hierarchical memory design (A12). "Working Memory" (the
current task's in-flight context) deliberately isn't stored here at all:
it belongs to the calling agent's own context window, not to brainstem --
this store only holds what should survive past one session. "Agent
Memory" (A12) is a thin `agent` scope column on the same facts table
rather than a separate store: an agent-scoped fact is still a fact, just
attributed to one profile instead of the whole repo, which is enough to
answer "what has *this* agent specifically learned" without standing up
parallel infrastructure for it. "Long-Term Knowledge" (A12) for a
single-repo tool is just this same table with no expiry -- there's no
separate cross-project store in V1.

Backs the plan's "no external DB required to run V1" requirement (Q10):
sqlite3 is stdlib, ships with Python, and needs no server process. Search
is LIKE-based full text for now -- deterministic and dependency-free. A
VectorStore-backed semantic search (see adapters/base.py) is a precision
upgrade for V2, not a V1 requirement: the plan's own research flagged that
LLM-built graphs are the wrong foundation (GraphRAG went into maintenance
mode for exactly this reason) and that deterministic retrieval should be
the default, with embeddings as an optional ranking boost.

Implements the `GraphBackend` adapter interface (`add_fact`/`query_facts`)
in addition to its own richer, more specific API (`record`/`search`/
`list`) -- found missing during a requirements audit: the interface
existed in adapters/base.py specifically so the memory backend could be
swapped (e.g. for a future Graphiti-backed implementation, per the plan's
"Open Decisions"), but nothing actually implemented it, so the
swappability claim was not true in practice. The
`record`/`search`/`list` methods remain the primary API for callers in
this codebase (mcp_server.py, cli.py) since they're more specific than
the generic interface; `add_fact`/`query_facts` exist so code written
against `GraphBackend` (a future caller that doesn't know it's talking to
sqlite specifically) also works.
"""

from __future__ import annotations

import sqlite3
import re
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from ..adapters.base import GraphBackend

# Split into tables-first, indexes-after (see _migrate_add_scope_column):
# an index on `scope` can't be created until the column is guaranteed to
# exist, and CREATE TABLE IF NOT EXISTS doesn't add columns to a table
# that predates them -- a fresh database gets the column from
# _TABLES_SCHEMA directly; an existing one gets it from the migration
# step, which must run before _INDEXES_SCHEMA either way.
_TABLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,          -- 'decision' | 'history' | 'rule' | 'proposal'
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    source TEXT,
    scope TEXT NOT NULL DEFAULT 'repo',   -- 'repo' (default, project-wide) or 'agent:<profile-name>'
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    outcome TEXT NOT NULL,       -- 'success' | 'failure' | 'unclear'
    notes TEXT NOT NULL DEFAULT '',
    source TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_references (
    fact_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    PRIMARY KEY (fact_id, path)
);
"""

_INDEXES_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_facts_kind ON facts(kind);
CREATE INDEX IF NOT EXISTS idx_facts_scope ON facts(scope);
CREATE INDEX IF NOT EXISTS idx_skill_usage_name ON skill_usage(skill_name);
CREATE INDEX IF NOT EXISTS idx_fact_references_fact_id ON fact_references(fact_id);
"""

VALID_KINDS = {"decision", "history", "rule", "proposal"}
VALID_OUTCOMES = {"success", "failure", "unclear"}
REPO_SCOPE = "repo"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def agent_scope(profile_name: str) -> str:
    return f"agent:{profile_name}"


def _migrate_add_scope_column(conn: sqlite3.Connection) -> None:
    """Existing .brain/memory/facts.db files predate the `scope` column
    (CREATE TABLE IF NOT EXISTS doesn't retroactively add columns) --
    add it in place rather than requiring a fresh database."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(facts)").fetchall()}
    if "scope" not in columns:
        conn.execute(f"ALTER TABLE facts ADD COLUMN scope TEXT NOT NULL DEFAULT '{REPO_SCOPE}'")
        conn.commit()


def _validate_references(references: list[tuple[str, str]] | None) -> list[tuple[str, str]]:
    """Validate metadata-only source references before storing them.

    Paths are repository-relative POSIX paths and hashes are SHA-256 source
    fingerprints. The store is intentionally unable to persist source content
    through this feature.
    """
    validated: list[tuple[str, str]] = []
    for path, content_hash in references or []:
        normalized = PurePosixPath(path)
        if not path or normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError(f"reference path must be a non-escaping relative path: {path!r}")
        if not _SHA256_RE.fullmatch(content_hash):
            raise ValueError("reference content_hash must be a lowercase SHA-256 hex digest")
        validated.append((normalized.as_posix(), content_hash))
    return validated


class MemoryStore(GraphBackend):
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        # WAL mode: readers don't block writers and vice versa, and commits
        # don't need a full fsync of the main DB file on every write --
        # Performance testing measured ~4.5ms/write under the default journal
        # mode (SQLite's per-commit fsync for durability), which is fine
        # for occasional use but unnecessarily slow for a tool meant to
        # record decisions/history frequently during an agent session.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_TABLES_SCHEMA)
        self._conn.commit()
        _migrate_add_scope_column(self._conn)
        self._conn.executescript(_INDEXES_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def record(
        self,
        kind: str,
        title: str,
        body: str,
        tags: list[str] | None = None,
        source: str | None = None,
        scope: str = REPO_SCOPE,
        references: list[tuple[str, str]] | None = None,
    ) -> int:
        if kind not in VALID_KINDS:
            raise ValueError(f"kind must be one of {VALID_KINDS}, got {kind!r}")
        references = _validate_references(references)
        cur = self._conn.execute(
            "INSERT INTO facts (kind, title, body, tags, source, scope, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kind, title, body, ",".join(tags or []), source, scope, datetime.now(timezone.utc).isoformat()),
        )
        fact_id = int(cur.lastrowid)
        if references:
            self._conn.executemany(
                "INSERT INTO fact_references (fact_id, path, content_hash) VALUES (?, ?, ?)",
                [(fact_id, path, content_hash) for path, content_hash in references],
            )
        self._conn.commit()
        return fact_id

    def references(self, fact_id: int) -> list[dict[str, str]]:
        """Return hash-bound source metadata for a durable fact, never source text."""
        rows = self._conn.execute(
            "SELECT path, content_hash FROM fact_references WHERE fact_id = ? ORDER BY path", (fact_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def search(
        self, query: str, kind: str | None = None, limit: int = 10, scope: str | None = None
    ) -> list[dict[str, Any]]:
        like = f"%{query}%"
        clauses = ["(title LIKE ? OR body LIKE ? OR tags LIKE ?)"]
        params: list[Any] = [like, like, like]
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM facts WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def list(self, kind: str | None = None, limit: int = 50, scope: str | None = None) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        where = f"WHERE {' AND '.join(clauses)} " if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM facts {where}ORDER BY created_at DESC LIMIT ?", params
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Skill memory: which skills actually helped, for which work. --

    def record_skill_usage(
        self, skill_name: str, outcome: str, notes: str = "", source: str | None = None
    ) -> int:
        if outcome not in VALID_OUTCOMES:
            raise ValueError(f"outcome must be one of {VALID_OUTCOMES}, got {outcome!r}")
        cur = self._conn.execute(
            "INSERT INTO skill_usage (skill_name, outcome, notes, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (skill_name, outcome, notes, source, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def skill_usage_stats(self, skill_name: str) -> dict[str, Any]:
        rows = self._conn.execute(
            "SELECT outcome, COUNT(*) as n FROM skill_usage WHERE skill_name = ? GROUP BY outcome",
            (skill_name,),
        ).fetchall()
        counts = {row["outcome"]: row["n"] for row in rows}
        total = sum(counts.values())
        return {
            "skill_name": skill_name,
            "total_uses": total,
            "success": counts.get("success", 0),
            "failure": counts.get("failure", 0),
            "unclear": counts.get("unclear", 0),
        }

    # -- GraphBackend interface (adapters/base.py) --

    def add_fact(self, kind: str, title: str, body: str, tags: list[str] | None = None) -> str:
        return str(self.record(kind, title, body, tags=tags))

    def query_facts(self, query: str, kind: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        return self.search(query, kind=kind, limit=limit)
