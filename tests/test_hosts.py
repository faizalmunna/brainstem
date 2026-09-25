import json

import pytest
from typer.testing import CliRunner

from brainstem.cli import app
from brainstem.hosts import render_connect_prompt, render_host_config, server_definition


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


def test_codex_config_is_explicit_and_least_privilege(tmp_path):
    rendered = render_host_config("codex", tmp_path)

    assert "[mcp_servers.brainstem]" in rendered
    assert '"readonly"' in rendered


def test_claude_code_uses_json_registration_to_preserve_child_flags(tmp_path):
    rendered = render_host_config("claude-code", tmp_path)

    assert "claude mcp add-json" in rendered
    assert '"--path"' in rendered


def test_unknown_host_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown host"):
        render_host_config("unknown", tmp_path)


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
