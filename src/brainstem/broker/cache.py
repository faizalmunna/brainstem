"""Exact-match request cache -- lever #2 in the plan's token-savings
ranking (Appendix Cluster B verdict): "Semantic/exact caching in front of
every LLM call... highest-ROI lever, provider-agnostic since it operates
on text pre-routing."

Semantic (embedding-similarity) caching is a natural follow-up once the
VectorStore adapter is in regular use (adapters/lancedb_store.py), but
exact caching alone already captures the common case of an agent re-asking
literally the same question (e.g. retried tool calls, repeated checks
across a session) -- so it's implemented first rather than skipped in
favor of the harder version.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    backend TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def cache_key(model: str, system: str | None, prompt: str) -> str:
    payload = f"{model}\x00{system or ''}\x00{prompt}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RequestCache:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")  # see memory/store.py's identical change for why
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> str | None:
        row = self._conn.execute("SELECT response FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return row["response"]

    def set(self, key: str, response: str, backend: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, response, backend, created_at) VALUES (?, ?, ?, ?)",
            (key, response, backend, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def stats(self) -> dict[str, int]:
        total = self.hits + self.misses
        return {"hits": self.hits, "misses": self.misses, "hit_rate_pct": round(100 * self.hits / total) if total else 0}
