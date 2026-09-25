import json

import pytest

import brainstem.retrieval.task_packet as task_packet
from brainstem.indexer.graph import build_graph
from brainstem.manifest import default_manifest, save_manifest
from brainstem.memory.store import MemoryStore
from brainstem.retrieval.task_packet import build_task_packet
from typer.testing import CliRunner

from brainstem.cli import app


def _packet(tmp_path, task: str = "Fix login token validation"):
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "app" / "tokens.py").write_text(
        "def validate_login_token(token: str) -> bool:\n    return bool(token)\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "login.py").write_text(
        "from app.tokens import validate_login_token\n\ndef login(token: str) -> bool:\n    return validate_login_token(token)\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "handlers.py").write_text(
        "from app.login import login\n\ndef dispatch(token: str) -> bool:\n    return login(token)\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_login.py").write_text(
        "def test_login_rejects_empty_token():\n    assert True\n",
        encoding="utf-8",
    )
    graph = build_graph(tmp_path, default_manifest("packet-repo"))
    memory = MemoryStore(tmp_path / ".brain" / "memory" / "facts.db")
    memory.record("rule", "No plaintext tokens", "Do not log tokens. API_KEY=real-secret-value")
    memory.record("history", "login token validation", "Previous token expiry regression.")
    packet = build_task_packet(tmp_path, graph, memory, task, max_chars=2_000)
    return packet, graph, memory


def test_task_packet_compiles_bounded_explainable_evidence(tmp_path):
    packet, _graph, memory = _packet(tmp_path)
    try:
        assert packet["packet_version"] == 1
        assert packet["evidence"]["excerpts"]
        assert any(item["file"] == "app/tokens.py" for item in packet["evidence"]["selected"])
        assert any(item["file"] == "app/handlers.py" for item in packet["evidence"]["impact_neighbors"])
        assert any(item["file"] == "tests/test_login.py" for item in packet["evidence"]["test_candidates"])
        assert packet["evidence"]["rules"][0]["title"] == "No plaintext tokens"
        assert "real-secret-value" not in json.dumps(packet)
        assert "API_KEY=[REDACTED]" in packet["evidence"]["rules"][0]["body"]
        assert packet["budget"]["source_chars"] <= 2_000
        assert packet["context_manifest"]["files"]
        assert "authentication or authorization" in packet["risk_signals"]
        assert packet["repository_state"]["freshness"]["index_current_for_packet"] is True
    finally:
        memory.close()


def test_task_packet_warns_when_graph_metadata_is_stale_but_uses_current_source(tmp_path):
    packet, _graph, memory = _packet(tmp_path)
    try:
        (tmp_path / "app" / "tokens.py").write_text(
            "def validate_login_token(token: str) -> bool:\n    return token == 'current'\n",
            encoding="utf-8",
        )
        stale_packet = build_task_packet(
            tmp_path,
            _graph,
            memory,
            "Fix login token validation",
            max_chars=2_000,
        )
        assert "app/tokens.py" in stale_packet["repository_state"]["freshness"]["stale_files"]
        assert stale_packet["repository_state"]["freshness"]["index_current_for_packet"] is False
        assert any("graph metadata is stale" in warning for warning in stale_packet["warnings"])
        source = "\n".join(item["content"] for item in stale_packet["evidence"]["excerpts"])
        assert "current" in source
    finally:
        memory.close()


def test_task_packet_rejects_invalid_task_and_respects_secret_exclusion(tmp_path):
    packet, graph, memory = _packet(tmp_path, task="login")
    try:
        (tmp_path / ".env").write_text("TOKEN=not-for-context", encoding="utf-8")
        with pytest.raises(ValueError, match="must not be empty"):
            build_task_packet(tmp_path, graph, memory, "")
        with pytest.raises(ValueError, match="at most"):
            build_task_packet(tmp_path, graph, memory, "x" * 4_001)
        assert "not-for-context" not in json.dumps(packet)
    finally:
        memory.close()


def test_task_packet_reports_only_git_changes_relevant_to_its_evidence(tmp_path, monkeypatch):
    _packet_result, graph, memory = _packet(tmp_path)
    monkeypatch.setattr(
        task_packet,
        "_git_state",
        lambda _root: {
            "available": True,
            "changed_files": ["app/tokens.py", "docs/unrelated.md"],
            "untracked_files": ["tests/test_login.py", "notes/private.md"],
            "sensitive_omitted": 0,
        },
    )
    try:
        packet = build_task_packet(tmp_path, graph, memory, "Fix login token validation", max_chars=2_000)
        state = packet["repository_state"]["git"]
        assert state["changed_file_count"] == 2
        assert state["untracked_file_count"] == 2
        assert "docs/unrelated.md" not in state["changed_files"]
        assert "notes/private.md" not in state["untracked_files"]
        assert "app/tokens.py" in state["changed_files"]
    finally:
        memory.close()


def test_task_packet_includes_compact_architecture_landmarks_for_broad_tasks(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (tmp_path / "src" / "main.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    (tmp_path / "tests" / "test_main.py").write_text("def test_main():\n    assert True\n", encoding="utf-8")
    graph = build_graph(tmp_path, default_manifest("landmarks"))
    memory = MemoryStore(tmp_path / ".brain" / "memory" / "facts.db")
    try:
        packet = build_task_packet(tmp_path, graph, memory, "orient me in this project", max_chars=2_000)
        landmarks = packet["project_landmarks"]
        assert {item["file"] for item in landmarks["entry_points"]} == {"src/main.py"}
        assert landmarks["test_roots"] == ["tests"]
        assert {item["path"] for item in landmarks["source_roots"]} == {"src", "tests"}
        assert landmarks["build_files"] == ["pyproject.toml"]
    finally:
        memory.close()


def test_task_packet_omits_stale_hash_bound_memory(tmp_path):
    _packet_result, graph, memory = _packet(tmp_path)
    try:
        memory.record(
            "history",
            "token validation decision",
            "Old implementation note",
            references=[("app/tokens.py", graph.files["app/tokens.py"].content_hash)],
        )
        current = build_task_packet(tmp_path, graph, memory, "token validation decision", max_chars=2_000)
        assert current["evidence"]["memory"][0]["freshness"] == "current"
        assert current["evidence"]["memory_freshness"] == {"current": 1, "unverified": 0, "stale_omitted": 0}

        (tmp_path / "app" / "tokens.py").write_text(
            "def validate_login_token(token: str) -> bool:\n    return token == 'new'\n",
            encoding="utf-8",
        )
        stale = build_task_packet(tmp_path, graph, memory, "token validation decision", max_chars=2_000)
        assert stale["evidence"]["memory"] == []
        assert stale["evidence"]["memory_freshness"]["stale_omitted"] == 1
        assert any("Stale hash-bound memory" in warning for warning in stale["warnings"])
    finally:
        memory.close()


def test_task_packet_enforces_a_whole_packet_budget_not_only_source_budget(tmp_path):
    _packet_result, graph, memory = _packet(tmp_path, task="token policy")
    try:
        for number in range(10):
            memory.record("rule", f"token policy {number}", "x" * 3_000)
        for number in range(5):
            memory.record("history", f"token policy history {number}", "y" * 3_000)

        packet = build_task_packet(
            tmp_path,
            graph,
            memory,
            "token policy",
            max_chars=2_000,
            max_packet_chars=6_000,
        )

        compact = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
        assert len(compact) <= 6_000
        assert packet["budget"]["packet_chars"] == len(compact)
        assert packet["budget"]["auxiliary_items_omitted"] > 0
        assert any("whole-packet" in warning for warning in packet["warnings"])
    finally:
        memory.close()


def test_prepare_cli_emits_packet_json(tmp_path):
    save_manifest(tmp_path, default_manifest("cli-packet"))
    (tmp_path / "service.py").write_text("def render_dashboard():\n    return 'ok'\n", encoding="utf-8")
    runner = CliRunner()
    indexed = runner.invoke(app, ["index", "--path", str(tmp_path)])
    assert indexed.exit_code == 0, indexed.output

    result = runner.invoke(
        app,
        ["prepare", "Fix dashboard rendering", "--path", str(tmp_path), "--no-semantic", "--max-chars", "500"],
    )
    assert result.exit_code == 0, result.output
    packet = json.loads(result.output)
    assert packet["task"] == "Fix dashboard rendering"
    assert packet["evidence"]["excerpts"][0]["file"] == "service.py"
