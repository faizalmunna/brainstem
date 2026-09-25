import json

import pytest
from typer.testing import CliRunner

from brainstem.cli import app
from brainstem.evaluation import evaluate_retrieval, load_evaluation_cases
from brainstem.indexer.graph import build_graph
from brainstem.manifest import default_manifest, save_manifest
from brainstem.memory.store import MemoryStore


def _write_case_file(tmp_path, cases):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"format_version": 1, "cases": cases}), encoding="utf-8")
    return path


def _build_repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "cache.py").write_text(
        "class RequestCache:\n    def invalidate(self):\n        pass\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_cache.py").write_text(
        "def test_request_cache_invalidates():\n    assert True\n",
        encoding="utf-8",
    )
    graph = build_graph(tmp_path, default_manifest("evaluation-repo"))
    memory = MemoryStore(tmp_path / ".brain" / "memory" / "facts.db")
    return graph, memory


def test_evaluate_retrieval_reports_quality_and_exact_packet_size(tmp_path):
    graph, memory = _build_repo(tmp_path)
    try:
        suite = load_evaluation_cases(
            _write_case_file(
                tmp_path,
                [
                    {
                        "id": "request-cache",
                        "query": "where is the request cache invalidated",
                        "required_files": ["src/cache.py"],
                    }
                ],
            )
        )
        report = evaluate_retrieval(tmp_path, graph, memory, suite, limit=5)

        assert report["summary"]["mean_recall_at_k"] == 1.0
        assert report["cases"][0]["first_relevant_rank"] == 1
        assert report["cases"][0]["packet_chars"] > 0
        assert report["method"]["token_measurement"].startswith("not measured")
    finally:
        memory.close()


def test_evaluation_case_loader_rejects_unsafe_or_duplicate_paths(tmp_path):
    unsafe = _write_case_file(
        tmp_path,
        [{"id": "unsafe", "query": "find secret", "required_files": ["../secret.py"]}],
    )
    with pytest.raises(ValueError, match="stay inside"):
        load_evaluation_cases(unsafe)

    duplicate = _write_case_file(
        tmp_path,
        [{"id": "duplicate", "query": "find cache", "required_files": ["src/cache.py", "src/cache.py"]}],
    )
    with pytest.raises(ValueError, match="repeats"):
        load_evaluation_cases(duplicate)


def test_evaluation_rejects_ground_truth_that_is_not_indexed(tmp_path):
    graph, memory = _build_repo(tmp_path)
    try:
        suite = load_evaluation_cases(
            _write_case_file(
                tmp_path,
                [{"id": "missing", "query": "find missing", "required_files": ["src/missing.py"]}],
            )
        )
        with pytest.raises(ValueError, match="present in the current index"):
            evaluate_retrieval(tmp_path, graph, memory, suite)
    finally:
        memory.close()


def test_evaluate_cli_uses_indexed_workspace_and_emits_json(tmp_path):
    save_manifest(tmp_path, default_manifest("evaluation-cli"))
    (tmp_path / "service.py").write_text("def validate_login_token():\n    pass\n", encoding="utf-8")
    cases = _write_case_file(
        tmp_path,
        [
            {
                "id": "login",
                "query": "validate login token",
                "required_files": ["service.py"],
            }
        ],
    )
    runner = CliRunner()
    indexed = runner.invoke(app, ["index", "--path", str(tmp_path)])
    assert indexed.exit_code == 0, indexed.output

    result = runner.invoke(
        app,
        ["evaluate", "--path", str(tmp_path), "--cases", str(cases), "--no-semantic"],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["summary"]["mean_recall_at_k"] == 1.0
