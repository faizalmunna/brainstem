import json

import pytest
from typer.testing import CliRunner

from brainstem.cli import app
from brainstem.integrations import inspect_connection, register_connection, render_connection
from brainstem.manifest import default_manifest, save_manifest


def _descriptor(path, **overrides):
    payload = {
        "name": "github",
        "transport": "streamable-http",
        "url": "https://mcp.example.test/github",
        "env_from": {"Authorization": "GITHUB_TOKEN"},
        "description": "Issue and pull-request tools",
        **overrides,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_mcp_catalog_renders_environment_references_not_credentials(tmp_path):
    descriptor = _descriptor(tmp_path / "github.json")
    connection = inspect_connection(descriptor)

    register_connection(tmp_path, connection)
    rendered = render_connection(tmp_path, "github")

    assert rendered["mcpServers"]["github"]["headers"] == {"Authorization": "${GITHUB_TOKEN}"}
    saved = (tmp_path / ".brain" / "integrations" / "mcp.json").read_text(encoding="utf-8")
    assert "GITHUB_TOKEN" in saved
    assert "ghp_" not in saved


def test_mcp_catalog_refuses_non_tls_remote_and_accidental_replace(tmp_path):
    insecure = _descriptor(tmp_path / "insecure.json", url="http://mcp.example.test")
    with pytest.raises(ValueError, match="https"):
        inspect_connection(insecure)

    connection = inspect_connection(_descriptor(tmp_path / "first.json"))
    register_connection(tmp_path, connection)
    with pytest.raises(FileExistsError, match="--replace"):
        register_connection(tmp_path, connection)


def test_mcp_cli_previews_before_explicit_registration(tmp_path):
    save_manifest(tmp_path, default_manifest("repo"))
    descriptor = _descriptor(tmp_path / "github.json")
    runner = CliRunner()

    preview = runner.invoke(app, ["mcp", "register", str(descriptor), "--path", str(tmp_path)])
    assert preview.exit_code == 0
    assert not (tmp_path / ".brain" / "integrations" / "mcp.json").exists()

    saved = runner.invoke(app, ["mcp", "register", str(descriptor), "--path", str(tmp_path), "--apply"])
    rendered = runner.invoke(app, ["mcp", "render", "github", "--path", str(tmp_path)])

    assert saved.exit_code == 0
    assert rendered.exit_code == 0
    assert "${GITHUB_TOKEN}" in rendered.output
