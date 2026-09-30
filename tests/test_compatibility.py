import json

import pytest
from typer.testing import CliRunner

from brainstem.cli import app
from brainstem.compatibility import enable_pack, inspect_pack, list_enabled_packs
from brainstem.manifest import default_manifest, save_manifest


def _pack(path):
    path.mkdir()
    (path / "package.json").write_text(
        json.dumps({"name": "example-pack", "version": "1.2.3", "license": "MIT", "skills": ["./skills"]}),
        encoding="utf-8",
    )
    (path / "skills").mkdir()


def test_pack_inspection_is_metadata_only_and_enable_requires_license_ack(tmp_path):
    source = tmp_path / "third-party-pack"
    _pack(source)
    pack = inspect_pack(source)

    assert pack.pack_id == "example-pack"
    assert pack.license == "MIT"
    with pytest.raises(PermissionError, match="accept-license"):
        enable_pack(tmp_path, pack, accept_license=False)

    enable_pack(tmp_path, pack, accept_license=True)
    assert list_enabled_packs(tmp_path)[0]["source_path"] == str(source.resolve())


def test_compatibility_cli_requires_explicit_license_acceptance(tmp_path):
    save_manifest(tmp_path, default_manifest("repo"))
    source = tmp_path / "pack"
    _pack(source)
    runner = CliRunner()

    preview = runner.invoke(app, ["compatibility", "check", str(source)])
    denied = runner.invoke(app, ["compatibility", "enable", str(source), "--path", str(tmp_path)])
    enabled = runner.invoke(
        app, ["compatibility", "enable", str(source), "--path", str(tmp_path), "--accept-license"]
    )

    assert preview.exit_code == 0
    assert '"license": "MIT"' in preview.output
    assert denied.exit_code == 1
    assert enabled.exit_code == 0


def test_explicit_workflow_pack_contract_rejects_unknown_hook_fields(tmp_path):
    source = tmp_path / "declared-pack"
    source.mkdir()
    (source / "brainstem.workflow.json").write_text(
        json.dumps(
            {
                "pack_id": "declared",
                "version": "1",
                "license": "MIT",
                "supported_capabilities": ["mcp", "workflow"],
                "hooks": ["do-not-run-me"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hooks"):
        inspect_pack(source)
