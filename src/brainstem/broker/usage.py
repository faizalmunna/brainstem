"""Privacy-preserving local completion-usage ledger.

The ledger records only timestamps, backend identifiers, estimated counts, and
cache status.  It intentionally never stores prompts, responses, API keys, or
cache keys, so it is safe to use as a local cost/efficiency trend signal.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS completion_usage (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    backend TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_hit INTEGER NOT NULL CHECK(cache_hit IN (0, 1))
);
"""


class UsageLedger:
    """Small SQLite ledger for aggregate broker efficiency reporting."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(self, *, backend: str, input_tokens: int, output_tokens: int, cache_hit: bool) -> None:
        self._conn.execute(
            "INSERT INTO completion_usage (created_at, backend, input_tokens, output_tokens, cache_hit) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), backend, input_tokens, output_tokens, int(cache_hit)),
        )
        self._conn.commit()

    def summary(self) -> dict[str, object]:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS requests,
                   COALESCE(SUM(cache_hit), 0) AS cache_hits,
                   COALESCE(SUM(input_tokens + output_tokens), 0) AS estimated_total_tokens,
                   COALESCE(SUM(CASE WHEN cache_hit = 0 THEN input_tokens + output_tokens ELSE 0 END), 0)
                     AS estimated_provider_tokens,
                   COALESCE(SUM(CASE WHEN cache_hit = 1 THEN input_tokens + output_tokens ELSE 0 END), 0)
                     AS estimated_tokens_avoided
            FROM completion_usage
            """
        ).fetchone()
        requests = int(row["requests"])
        by_backend = [
            dict(item)
            for item in self._conn.execute(
                """
                SELECT backend, COUNT(*) AS requests, SUM(cache_hit) AS cache_hits,
                       SUM(input_tokens + output_tokens) AS estimated_total_tokens
                FROM completion_usage GROUP BY backend ORDER BY backend
                """
            ).fetchall()
        ]
        return {
            "requests": requests,
            "cache_hits": int(row["cache_hits"]),
            "cache_hit_rate_pct": round(100 * int(row["cache_hits"]) / requests) if requests else 0,
            "estimated_total_tokens": int(row["estimated_total_tokens"]),
            "estimated_provider_tokens": int(row["estimated_provider_tokens"]),
            "estimated_tokens_avoided": int(row["estimated_tokens_avoided"]),
            "by_backend": by_backend,
            "accounting": "portable character estimate; provider invoices and tokenizer counts may differ",
        }
