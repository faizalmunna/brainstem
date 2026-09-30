import json

import pytest
from typer.testing import CliRunner

from brainstem.cli import app
from brainstem.sbom import generate_sbom


def _write_lock(root):
    (root / "pyproject.toml").write_text("[project]\nname = \"demo\"\nversion = \"1.0.0\"\n", encoding="utf-8")
    (root / "uv.lock").write_text(
        """version = 1
[[package]]
name = "demo"
version = "1.0.0"
dependencies = [{ name = "alpha" }]
[package.optional-dependencies]
feature = [{ name = "beta" }]
[[package]]
name = "alpha"
version = "2.0.0"
dependencies = [{ name = "shared" }]
sdist = { hash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
[[package]]
name = "beta"
version = "3.0.0"
[[package]]
name = "shared"
version = "4.0.0"
""",
        encoding="utf-8",
    )


def test_sbom_uses_only_default_runtime_dependencies_unless_extra_selected(tmp_path):
    _write_lock(tmp_path)

    default = generate_sbom(tmp_path)
    with_feature = generate_sbom(tmp_path, ("feature",))

    assert [component["name"] for component in default["components"]] == ["alpha", "shared"]
    assert [component["name"] for component in with_feature["components"]] == ["alpha", "beta", "shared"]
    assert default == generate_sbom(tmp_path)
    assert default["components"][0]["hashes"][0]["alg"] == "SHA-256"


def test_sbom_rejects_unknown_extra(tmp_path):
    _write_lock(tmp_path)

    with pytest.raises(ValueError, match="Unknown uv.lock extra"):
        generate_sbom(tmp_path, ("missing",))


def test_sbom_preserves_platform_specific_lock_variants(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"demo\"\nversion = \"1.0.0\"\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text(
        """version = 1
[[package]]
name = "demo"
version = "1.0.0"
dependencies = [{ name = "gamma" }]
[[package]]
name = "gamma"
version = "1.0.0"
resolution-markers = ["sys_platform == 'win32'"]
[[package]]
name = "gamma"
version = "2.0.0"
resolution-markers = ["sys_platform != 'win32'"]
""",
        encoding="utf-8",
    )

    bom = generate_sbom(tmp_path)

    gamma = [component for component in bom["components"] if component["name"] == "gamma"]
    assert [component["version"] for component in gamma] == ["1.0.0", "2.0.0"]
    assert len({component["bom-ref"] for component in gamma}) == 2
    assert all(component["properties"][0]["name"] == "brainstem:uv-resolution-markers" for component in gamma)


def test_sbom_cli_writes_json(tmp_path):
    _write_lock(tmp_path)
    result = CliRunner().invoke(app, ["sbom", "--path", str(tmp_path), "--output", "evidence/bom.json"])

    output = tmp_path / "evidence" / "bom.json"
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text(encoding="utf-8"))["bomFormat"] == "CycloneDX"
