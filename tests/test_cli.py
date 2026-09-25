"""CLI smoke tests. Every command below takes `--path`/`-p` for the target
repo (not a positional argument) -- this suite exists specifically to catch
the kind of inconsistency where one command drifts from that convention
(happened once already: `init`/`index` originally took a positional path
while every other command used `--path`)."""

from typer.testing import CliRunner

from brainstem.cli import app

runner = CliRunner()


def test_init_creates_manifest(tmp_path):
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".brain" / "brain.toml").exists()


def test_init_is_idempotent(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "Already initialized" in result.output


def test_index_then_query_finds_a_symbol(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    (tmp_path / "widgets.py").write_text("def render_widget():\n    pass\n", encoding="utf-8")

    index_result = runner.invoke(app, ["index", "--path", str(tmp_path)])
    assert index_result.exit_code == 0, index_result.output
    assert "1 files" in index_result.output

    query_result = runner.invoke(app, ["query", "render_widget", "--path", str(tmp_path)])
    assert query_result.exit_code == 0, query_result.output
    assert "widgets.py" in query_result.output


def test_query_without_index_fails_cleanly(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    result = runner.invoke(app, ["query", "anything", "--path", str(tmp_path)])
    assert result.exit_code == 1
    assert "No index found" in result.output


def test_record_and_rules_round_trip(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    runner.invoke(app, ["record", "rule", "no-secrets", "Never commit .env files", "--path", str(tmp_path)])

    result = runner.invoke(app, ["rules", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "no-secrets" in result.output
    assert "Never commit .env files" in result.output


def test_record_hash_binds_indexed_source_references(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    (tmp_path / "service.py").write_text("def run():\n    pass\n", encoding="utf-8")
    assert runner.invoke(app, ["index", "--path", str(tmp_path)]).exit_code == 0

    result = runner.invoke(
        app,
        ["record", "decision", "service choice", "Use the service layer", "--paths", "service.py", "--path", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "1 source reference" in result.output


def test_skills_lists_bundled_skills(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    result = runner.invoke(app, ["skills", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "repo-exploration" in result.output


def test_agent_create_then_list(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    create_result = runner.invoke(
        app, ["agent", "create", "reviewer", "--permissions", "READ", "--path", str(tmp_path)]
    )
    assert create_result.exit_code == 0, create_result.output

    list_result = runner.invoke(app, ["agent", "list", "--path", str(tmp_path)])
    assert list_result.exit_code == 0
    assert "reviewer" in list_result.output
    assert "READ" in list_result.output


def test_skill_install_then_visible_in_list(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    source = tmp_path / "external-pack"
    (source).mkdir()
    (source / "custom.md").write_text(
        "---\nname: custom-skill\ndescription: test\ntriggers: []\npermissions: [READ]\n---\n\nBody.\n",
        encoding="utf-8",
    )

    install_result = runner.invoke(app, ["skill", "install", str(source), "--path", str(tmp_path)])
    assert install_result.exit_code == 0, install_result.output

    list_result = runner.invoke(app, ["skills", "--path", str(tmp_path)])
    assert "custom-skill" in list_result.output
    assert "external-pack" in list_result.output


def test_skill_disable_hides_then_enable_restores(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    (tmp_path / ".brain" / "skills").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".brain" / "skills" / "custom.md").write_text(
        "---\nname: toggle-me\ndescription: test\ntriggers: []\npermissions: [READ]\n---\n\nBody.\n",
        encoding="utf-8",
    )

    before = runner.invoke(app, ["skills", "--path", str(tmp_path)])
    assert "toggle-me" in before.output

    disable_result = runner.invoke(app, ["skill", "disable", "toggle-me", "--path", str(tmp_path)])
    assert disable_result.exit_code == 0, disable_result.output

    after_disable = runner.invoke(app, ["skills", "--path", str(tmp_path)])
    assert "toggle-me" not in after_disable.output

    all_result = runner.invoke(app, ["skills", "--all", "--path", str(tmp_path)])
    assert "toggle-me [disabled]" in all_result.output

    enable_result = runner.invoke(app, ["skill", "enable", "toggle-me", "--path", str(tmp_path)])
    assert enable_result.exit_code == 0

    after_enable = runner.invoke(app, ["skills", "--path", str(tmp_path)])
    assert "toggle-me" in after_enable.output


def test_skill_disable_unknown_name_fails_cleanly(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    result = runner.invoke(app, ["skill", "disable", "not-a-real-skill", "--path", str(tmp_path)])
    assert result.exit_code == 1
    assert "No skill named" in result.output


def test_skill_remove_uninstalls_pack(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    source = tmp_path / "external-pack"
    source.mkdir()
    (source / "x.md").write_text(
        "---\nname: x\ndescription: test\ntriggers: []\npermissions: [READ]\n---\n\nBody.\n", encoding="utf-8"
    )
    runner.invoke(app, ["skill", "install", str(source), "--path", str(tmp_path)])

    remove_result = runner.invoke(app, ["skill", "remove", "external-pack", "--path", str(tmp_path)])
    assert remove_result.exit_code == 0, remove_result.output

    list_result = runner.invoke(app, ["skills", "--path", str(tmp_path)])
    assert "external-pack" not in list_result.output


def test_skill_usage_record_then_stats(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])

    record_result = runner.invoke(
        app, ["skill", "record-usage", "some-skill", "success", "--notes", "worked great", "--path", str(tmp_path)]
    )
    assert record_result.exit_code == 0, record_result.output

    stats_result = runner.invoke(app, ["skill", "usage-stats", "some-skill", "--path", str(tmp_path)])
    assert stats_result.exit_code == 0
    assert "1 uses" in stats_result.output
    assert "1 success" in stats_result.output


def test_skill_usage_record_invalid_outcome_fails_cleanly(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    result = runner.invoke(app, ["skill", "record-usage", "x", "not-a-real-outcome", "--path", str(tmp_path)])
    assert result.exit_code == 1


def test_workflow_cli_enforces_evidence_gates(tmp_path):
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    start = runner.invoke(
        app, ["workflow", "start", "Fix login redirect", "--id", "login-flow", "--path", str(tmp_path)]
    )
    assert start.exit_code == 0, start.output

    for state in ["context_ready", "design_review"]:
        result = runner.invoke(app, ["workflow", "transition", "login-flow", state, "--path", str(tmp_path)])
        assert result.exit_code == 0, result.output
    design = runner.invoke(
        app, ["workflow", "artifact", "login-flow", "design", "docs/design.md", "--status", "approved", "--path", str(tmp_path)]
    )
    assert design.exit_code == 0, design.output
    result = runner.invoke(app, ["workflow", "transition", "login-flow", "planned", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    plan = runner.invoke(app, ["workflow", "artifact", "login-flow", "plan", "docs/plan.md", "--path", str(tmp_path)])
    assert plan.exit_code == 0, plan.output
    test_plan = runner.invoke(
        app, ["workflow", "artifact", "login-flow", "test_plan", "tests/test_auth.py", "--path", str(tmp_path)]
    )
    assert test_plan.exit_code == 0, test_plan.output
    result = runner.invoke(app, ["workflow", "transition", "login-flow", "implementing", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    implementation = runner.invoke(
        app, ["workflow", "artifact", "login-flow", "implementation", "src/auth.py", "--path", str(tmp_path)]
    )
    assert implementation.exit_code == 0, implementation.output
    result = runner.invoke(app, ["workflow", "transition", "login-flow", "verification", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output

    missing_evidence = runner.invoke(app, ["workflow", "transition", "login-flow", "review", "--path", str(tmp_path)])
    assert missing_evidence.exit_code == 1
    assert "passed verification" in missing_evidence.output

    verified = runner.invoke(
        app, ["workflow", "verify", "login-flow", "pytest: 104 passed", "--passed", "--path", str(tmp_path)]
    )
    assert verified.exit_code == 0, verified.output
    still_manual = runner.invoke(app, ["workflow", "transition", "login-flow", "review", "--path", str(tmp_path)])
    assert still_manual.exit_code == 1
    assert "passed verification" in still_manual.output


def test_ask_fails_cleanly_with_no_backend_available(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner.invoke(app, ["init", "--path", str(tmp_path)])

    result = runner.invoke(app, ["ask", "hello", "--path", str(tmp_path), "--ollama-model", "definitely-not-a-real-model"])
    assert result.exit_code == 1
    assert "No configured ModelBackend is available" in result.output
