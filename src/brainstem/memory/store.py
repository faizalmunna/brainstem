"""Embedded, durable repository memory backed by SQLite.

It records decisions, rules, history, source-reference hashes, and skill-use
outcomes without requiring an external service. The store also implements the
generic :class:`GraphBackend` interface, while retaining its richer local API.
"""

from __future__ import annotations

import sqlite3
import re
import threading
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
    seen_paths: set[str] = set()
    for path, content_hash in references or []:
        normalized = PurePosixPath(path)
        if not path or normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError(f"reference path must be a non-escaping relative path: {path!r}")
        if not _SHA256_RE.fullmatch(content_hash):
            raise ValueError("reference content_hash must be a lowercase SHA-256 hex digest")
        normalized_path = normalized.as_posix()
        if normalized_path in seen_paths:
            raise ValueError(f"reference path is duplicated: {normalized_path!r}")
        seen_paths.add(normalized_path)
        validated.append((normalized_path, content_hash))
    return validated


class MemoryStore(GraphBackend):
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # MCP hosts can dispatch synchronous tools from more than one worker
        # thread. Serializing this single connection keeps those calls safe,
        # while SQLite's busy timeout lets separate Brainstem processes wait
        # briefly for a legitimate WAL writer instead of failing immediately.
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
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
        with self._lock:
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
        with self._lock, self._conn:
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
        return fact_id

    def references(self, fact_id: int) -> list[dict[str, str]]:
        """Return hash-bound source metadata for a durable fact, never source text."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT path, content_hash FROM fact_references WHERE fact_id = ? ORDER BY path", (fact_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def search(
        self, query: str, kind: str | None = None, limit: int = 10, scope: str | None = None
    ) -> list[dict[str, Any]]:
        like = f"%{query}%"
        if kind and scope:
            statement = (
                "SELECT * FROM facts WHERE (title LIKE ? OR body LIKE ? OR tags LIKE ?) "
                "AND kind = ? AND scope = ? ORDER BY created_at DESC LIMIT ?"
            )
            params: tuple[Any, ...] = (like, like, like, kind, scope, limit)
        elif kind:
            statement = (
                "SELECT * FROM facts WHERE (title LIKE ? OR body LIKE ? OR tags LIKE ?) "
                "AND kind = ? ORDER BY created_at DESC LIMIT ?"
            )
            params = (like, like, like, kind, limit)
        elif scope:
            statement = (
                "SELECT * FROM facts WHERE (title LIKE ? OR body LIKE ? OR tags LIKE ?) "
                "AND scope = ? ORDER BY created_at DESC LIMIT ?"
            )
            params = (like, like, like, scope, limit)
        else:
            statement = "SELECT * FROM facts WHERE (title LIKE ? OR body LIKE ? OR tags LIKE ?) ORDER BY created_at DESC LIMIT ?"
            params = (like, like, like, limit)
        with self._lock:
            rows = self._conn.execute(statement, params).fetchall()
        return [dict(r) for r in rows]

    def list(self, kind: str | None = None, limit: int = 50, scope: str | None = None) -> list[dict[str, Any]]:
        if kind and scope:
            statement = "SELECT * FROM facts WHERE kind = ? AND scope = ? ORDER BY created_at DESC LIMIT ?"
            params: tuple[Any, ...] = (kind, scope, limit)
        elif kind:
            statement = "SELECT * FROM facts WHERE kind = ? ORDER BY created_at DESC LIMIT ?"
            params = (kind, limit)
        elif scope:
            statement = "SELECT * FROM facts WHERE scope = ? ORDER BY created_at DESC LIMIT ?"
            params = (scope, limit)
        else:
            statement = "SELECT * FROM facts ORDER BY created_at DESC LIMIT ?"
            params = (limit,)
        with self._lock:
            rows = self._conn.execute(statement, params).fetchall()
        return [dict(r) for r in rows]

    # -- Skill memory: which skills actually helped, for which work. --

    def record_skill_usage(
        self, skill_name: str, outcome: str, notes: str = "", source: str | None = None
    ) -> int:
        if outcome not in VALID_OUTCOMES:
            raise ValueError(f"outcome must be one of {VALID_OUTCOMES}, got {outcome!r}")
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO skill_usage (skill_name, outcome, notes, source, created_at) VALUES (?, ?, ?, ?, ?)",
                (skill_name, outcome, notes, source, datetime.now(timezone.utc).isoformat()),
            )
        return cur.lastrowid  # type: ignore[return-value]

    def skill_usage_stats(self, skill_name: str) -> dict[str, Any]:
        with self._lock:
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
