import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brainstem.cli import app
from brainstem.diagnostics import run_mcp_handshake
from brainstem.hosts import (
    host_status,
    host_cli_status,
    install_host_config,
    remove_host_config,
    render_connect_prompt,
    render_host_config,
    server_definition,
)
from brainstem.manifest import default_manifest, save_manifest


def test_cursor_config_is_valid_project_mcp_json(tmp_path):
    rendered = render_host_config("cursor", tmp_path, profile="readonly")
    config = json.loads(rendered.split("\n", 1)[1])

    assert config["mcpServers"]["brainstem"]["command"] == "brainstem"
    assert config["mcpServers"]["brainstem"]["args"][-1] == "readonly"


def test_vscode_uses_servers_root_key(tmp_path):
    rendered = render_host_config("vscode", tmp_path)
    config = json.loads(rendered.split("\n", 1)[1])

    assert "servers" in config
    assert "mcpServers" not in config


def test_vscode_user_scope_uses_documented_portable_agent_host_path(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    written = install_host_config("vscode", tmp_path / "repo", scope="user")
    config = json.loads(written.read_text(encoding="utf-8"))

    assert written == tmp_path / ".copilot" / "mcp-config.json"
    assert "mcpServers" in config


def test_opencode_uses_its_local_mcp_schema(tmp_path):
    rendered = render_host_config("opencode", tmp_path)
    config = json.loads(rendered.split("\n", 1)[1])

    entry = config["mcp"]["brainstem"]
    assert config["$schema"] == "https://opencode.ai/config.json"
    assert entry["type"] == "local"
    assert entry["command"][:2] == ["brainstem", "serve"]
    assert entry["enabled"] is True


def test_opencode_install_preserves_its_top_level_configuration_and_status(tmp_path):
    config_path = tmp_path / "opencode.json"
    config_path.write_text(json.dumps({"$schema": "https://opencode.ai/config.json", "plugin": ["other"]}), encoding="utf-8")

    written = install_host_config("opencode", tmp_path)
    config = json.loads(written.read_text(encoding="utf-8"))
    assert config["plugin"] == ["other"]
    assert config["mcp"]["brainstem"]["type"] == "local"
    assert host_status("opencode", tmp_path)["configured"] is True

    remove_host_config("opencode", tmp_path)
    assert json.loads(written.read_text(encoding="utf-8"))["plugin"] == ["other"]


def test_qwen_code_uses_project_settings_and_standard_stdio_schema(tmp_path):
    written = install_host_config("qwen-code", tmp_path)
    config = json.loads(written.read_text(encoding="utf-8"))

    assert written == tmp_path / ".qwen" / "settings.json"
    assert config["mcpServers"]["brainstem"] == server_definition(tmp_path)


def test_copilot_cli_is_honestly_user_scoped(tmp_path):
    with pytest.raises(ValueError, match="user-scoped"):
        install_host_config("copilot-cli", tmp_path)


def test_copilot_cli_writes_only_its_documented_user_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    written = install_host_config("copilot-cli", tmp_path / "repo", scope="user")
    config = json.loads(written.read_text(encoding="utf-8"))
    assert written == tmp_path / ".copilot" / "mcp-config.json"
    assert config["mcpServers"]["brainstem"]["command"] == "brainstem"


def test_codex_config_is_explicit_and_least_privilege(tmp_path):
    rendered = render_host_config("codex", tmp_path)

    assert "[mcp_servers.brainstem]" in rendered
    assert '"readonly"' in rendered
    assert "~/.codex/config.toml" in rendered


def test_codex_refuses_an_unproven_project_config_path(tmp_path):
    with pytest.raises(ValueError, match="user-scoped"):
        install_host_config("codex", tmp_path, scope="project")


def test_codex_config_refuses_malformed_toml_without_changing_it(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    malformed = "[mcp_servers\n"
    config.write_text(malformed, encoding="utf-8")

    with pytest.raises(ValueError, match="invalid TOML"):
        install_host_config("codex", tmp_path / "repo", scope="user")

    assert config.read_text(encoding="utf-8") == malformed


def test_host_doctor_runs_the_real_local_stdio_handshake(tmp_path):
    save_manifest(tmp_path, default_manifest("doctor-smoke"))

    # Run outside Typer's output-capturing CliRunner: inherited file handles
    # under capture have no OS fileno on Windows, whereas a host doctor runs
    # from a real terminal.
    report = run_mcp_handshake(tmp_path)

    assert report["passed"] is True, report
    assert report["missing_tools"] == []


def test_claude_code_uses_json_registration_to_preserve_child_flags(tmp_path):
    rendered = render_host_config("claude-code", tmp_path)

    assert "claude mcp add-json" in rendered
    assert '"--path"' in rendered


def test_unknown_host_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown host"):
        render_host_config("unknown", tmp_path)


def test_host_cli_status_is_descriptive_until_a_doctor_explicitly_probes_it():
    status = host_cli_status("generic")

    assert status == {"applicable": False, "available": None, "executable": None, "version": None}


def test_generic_config_is_portable_stdio_definition(tmp_path):
    rendered = render_host_config("generic", tmp_path)
    config = json.loads(rendered.split("\n", 1)[1])

    assert config["mcpServers"]["brainstem"] == server_definition(tmp_path)
    assert config["mcpServers"]["brainstem"]["args"][0] == "serve"


def test_connect_prompt_preserves_readonly_stdio_boundary(tmp_path):
    prompt = render_connect_prompt(tmp_path)

    assert "local stdio MCP" in prompt
    assert "Do not expose it over HTTP" in prompt
    assert '"readonly"' in prompt
    assert "describe_project" in prompt
    assert "prepare_task" in prompt
    assert "expand context only" in prompt


def test_host_config_cli_prints_without_writing(tmp_path):
    result = CliRunner().invoke(app, ["host", "config", "gemini", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert '"mcpServers"' in result.output


def test_connect_prompt_cli_prints_without_writing(tmp_path):
    result = CliRunner().invoke(app, ["host", "connect-prompt", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "local stdio MCP" in result.output


def test_host_install_preserves_other_json_servers_and_uninstall_removes_only_brainstem(tmp_path):
    config_path = tmp_path / ".cursor" / "mcp.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}), encoding="utf-8")

    written = install_host_config("cursor", tmp_path)
    configured = json.loads(written.read_text(encoding="utf-8"))
    assert set(configured["mcpServers"]) == {"other", "brainstem"}
    assert host_status("cursor", tmp_path)["configured"] is True

    remove_host_config("cursor", tmp_path)
    remaining = json.loads(written.read_text(encoding="utf-8"))
    assert remaining["mcpServers"] == {"other": {"command": "other"}}


def test_host_status_marks_a_modified_brainstem_entry_invalid(tmp_path):
    config_path = tmp_path / ".cursor" / "mcp.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps({"mcpServers": {"brainstem": {"command": "unexpected", "args": []}}}), encoding="utf-8"
    )

    status = host_status("cursor", tmp_path)

    assert status["configured"] is False
    assert "command does not match" in str(status["entry_error"])


def test_host_config_rejects_an_invalid_profile_name(tmp_path):
    with pytest.raises(ValueError, match="profile must"):
        install_host_config("cursor", tmp_path, profile="../escape")


def test_host_install_cli_is_preview_first(tmp_path):
    runner = CliRunner()
    preview = runner.invoke(app, ["host", "install", "cursor", "--path", str(tmp_path)])
    assert preview.exit_code == 0
    assert "Preview only" in preview.output
    assert not (tmp_path / ".cursor" / "mcp.json").exists()

    applied = runner.invoke(app, ["host", "install", "cursor", "--path", str(tmp_path), "--apply"])
    assert applied.exit_code == 0
    assert (tmp_path / ".cursor" / "mcp.json").is_file()


def test_host_install_refuses_a_symlinked_config_parent(tmp_path):
    outside = tmp_path.parent / "outside-host-config"
    outside.mkdir(exist_ok=True)
    try:
        (tmp_path / ".cursor").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this test host")

    with pytest.raises(ValueError, match="outside the selected project scope"):
        install_host_config("cursor", tmp_path)
