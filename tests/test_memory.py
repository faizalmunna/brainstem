import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from brainstem.adapters.base import GraphBackend
from brainstem.memory.store import REPO_SCOPE, MemoryStore, agent_scope


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(tmp_path / "facts.db")
    yield s
    s.close()


def test_memory_store_is_a_real_graphbackend(store):
    # Found missing in a requirements audit: the interface existed but
    # nothing implemented it, so the "swappable memory backend" claim
    # wasn't actually true. This is the regression test for that fix.
    assert isinstance(store, GraphBackend)


def test_record_and_search(store):
    store.record("decision", "use postgres", "chose postgres over mysql for jsonb support")
    results = store.search("postgres")
    assert len(results) == 1
    assert results[0]["title"] == "use postgres"


def test_fact_references_are_hash_bound_and_validate_path_safety(store):
    digest = "a" * 64
    fact_id = store.record("decision", "use postgres", "reason", references=[("src/db.py", digest)])

    assert store.references(fact_id) == [{"path": "src/db.py", "content_hash": digest}]
    with pytest.raises(ValueError, match="non-escaping"):
        store.record("decision", "bad", "bad", references=[("../secret", digest)])
    with pytest.raises(ValueError, match="SHA-256"):
        store.record("decision", "bad", "bad", references=[("src/db.py", "not-a-hash")])
    with pytest.raises(ValueError, match="duplicated"):
        store.record("decision", "bad", "bad", references=[("src/db.py", digest), ("src/db.py", digest)])
    assert store.search("bad") == []


def test_memory_store_serializes_shared_connection_access_across_threads(store):
    with ThreadPoolExecutor(max_workers=8) as executor:
        identifiers = list(
            executor.map(
                lambda number: store.record("history", f"event-{number}", "concurrent write"),
                range(40),
            )
        )

    assert len(set(identifiers)) == 40
    assert len(store.search("concurrent write", limit=50)) == 40


def test_search_scoped_by_kind(store):
    store.record("decision", "a", "body a")
    store.record("history", "b", "body b")

    assert len(store.search("body", kind="decision")) == 1
    assert len(store.search("body", kind="history")) == 1
    assert len(store.search("body")) == 2


def test_invalid_kind_rejected(store):
    with pytest.raises(ValueError):
        store.record("not-a-real-kind", "x", "y")


def test_list_orders_newest_first(store):
    store.record("rule", "first", "x")
    store.record("rule", "second", "y")

    results = store.list(kind="rule")
    assert [r["title"] for r in results] == ["second", "first"]


def test_graphbackend_methods_are_real_not_stubs(store):
    fact_id = store.add_fact("decision", "graphbackend title", "graphbackend body")
    assert isinstance(fact_id, str)

    results = store.query_facts("graphbackend")
    assert len(results) == 1
    assert results[0]["title"] == "graphbackend title"

    # add_fact/query_facts and record/search operate on the same table --
    # not two parallel, silently-diverging implementations.
    assert store.search("graphbackend") == results


# --- memory hierarchy: scope (Agent Memory tier) ---


def test_default_scope_is_repo(store):
    store.record("rule", "a", "b")
    assert store.list()[0]["scope"] == REPO_SCOPE


def test_agent_scoped_fact_is_isolated_from_repo_scope(store):
    store.record("decision", "repo-wide", "x", scope=REPO_SCOPE)
    store.record("decision", "architect-only", "y", scope=agent_scope("architect"))

    assert [r["title"] for r in store.list(scope=REPO_SCOPE)] == ["repo-wide"]
    assert [r["title"] for r in store.list(scope=agent_scope("architect"))] == ["architect-only"]
    assert len(store.list()) == 2  # unscoped list still sees both


def test_search_can_be_scoped_to_one_agent(store):
    store.record("history", "shared bug", "seen everywhere", scope=REPO_SCOPE)
    store.record("history", "shared bug", "architect's specific angle", scope=agent_scope("architect"))

    results = store.search("shared bug", scope=agent_scope("architect"))
    assert len(results) == 1
    assert results[0]["body"] == "architect's specific angle"


def test_existing_database_without_scope_column_is_migrated(tmp_path):
    db_path = tmp_path / "old_facts.db"
    # Simulate a facts.db created before the scope column existed.
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE facts (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, title TEXT NOT NULL, "
        "body TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '', source TEXT, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO facts (kind, title, body, tags, source, created_at) VALUES ('rule', 'old', 'x', '', NULL, '2026-01-01')"
    )
    conn.commit()
    conn.close()

    store = MemoryStore(db_path)  # should migrate in place, not raise
    try:
        rows = store.list()
        assert len(rows) == 1
        assert rows[0]["scope"] == REPO_SCOPE  # backfilled default for pre-existing rows
        store.record("rule", "new", "y")  # confirm writes still work post-migration
        assert len(store.list()) == 2
    finally:
        store.close()


# --- skill memory ---


def test_record_and_query_skill_usage(store):
    store.record_skill_usage("react-hydration-mismatch", "success", notes="fixed in 10 min")
    store.record_skill_usage("react-hydration-mismatch", "success")
    store.record_skill_usage("react-hydration-mismatch", "failure", notes="didn't apply here")

    stats = store.skill_usage_stats("react-hydration-mismatch")
    assert stats == {
        "skill_name": "react-hydration-mismatch",
        "total_uses": 3,
        "success": 2,
        "failure": 1,
        "unclear": 0,
    }


def test_skill_usage_stats_for_unused_skill_is_zeroed(store):
    stats = store.skill_usage_stats("never-used-skill")
    assert stats["total_uses"] == 0


def test_invalid_skill_usage_outcome_rejected(store):
    with pytest.raises(ValueError):
        store.record_skill_usage("some-skill", "not-a-real-outcome")
