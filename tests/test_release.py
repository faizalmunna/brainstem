import json

from typer.testing import CliRunner

from brainstem.cli import app
from brainstem.release import release_readiness


def _write_release_files(root):
    (root / "npm").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "src" / "brainstem").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        """[project]\nname = \"brainstem\"\nversion = \"1.2.3\"\n[project.urls]\nRepository = \"https://github.com/example/brainstem\"\n""",
        encoding="utf-8",
    )
    (root / "npm" / "package.json").write_text(
        json.dumps({"version": "1.2.3", "repository": "https://github.com/example/brainstem"}), encoding="utf-8"
    )
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (root / "SECURITY.md").write_text("Report issues to security@example.test\n", encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "ubuntu-latest\nmacos-latest\nwindows-latest\nnpm install\nbrainstem sbom\n"
        "startsWith(github.ref, 'refs/tags/v')\n"
        "needs: [security, python, npm-wrapper, docker-image]\n"
        "uses: ./.github/workflows/release-artifacts.yml\n"
        "docker/setup-qemu-action@v3\n--platform linux/arm64\nMCP_TEST_TIMEOUT_S=60\n",
        encoding="utf-8",
    )
    (root / ".github" / "workflows" / "release-artifacts.yml").write_text(
        "workflow_call:\nid-token: write\nattestations: write\nactions/attest@v4\nsubject-path\nsbom-path\n",
        encoding="utf-8",
    )
    (root / ".github" / "workflows" / "codeql.yml").write_text(
        "github/codeql-action/init@v4\ngithub/codeql-action/analyze@v4\nsecurity-events: write\npython\njavascript-typescript\n",
        encoding="utf-8",
    )
    (root / "src" / "brainstem" / "sbom.py").write_text("# generator\n", encoding="utf-8")


def test_release_check_fails_closed_for_missing_release_identity(tmp_path):
    report = release_readiness(tmp_path)

    assert report.ready is False
    assert any(check.name == "Git origin remote" and not check.passed for check in report.checks)
    assert any(check.name == "npm repository metadata" and not check.passed for check in report.checks)


def test_release_check_accepts_complete_source_controls(tmp_path, monkeypatch):
    _write_release_files(tmp_path)

    def fake_git(_root, *args):
        if args == ("remote", "get-url", "origin"):
            return "https://github.com/example/brainstem"
        if args == ("status", "--porcelain=v1"):
            return ""
        return None

    monkeypatch.setattr("brainstem.release._git", fake_git)
    report = release_readiness(tmp_path)

    assert report.ready is True
    assert any(check.name == "Tag-gated cross-platform release" and check.passed for check in report.checks)
    assert any(check.name == "Cross-architecture Docker configuration" and check.passed for check in report.checks)


def test_release_check_rejects_mismatched_repository_identity(tmp_path, monkeypatch):
    _write_release_files(tmp_path)

    def fake_git(_root, *args):
        if args == ("remote", "get-url", "origin"):
            return "git@github.com:other/brainstem.git"
        if args == ("status", "--porcelain=v1"):
            return ""
        return None

    monkeypatch.setattr("brainstem.release._git", fake_git)

    report = release_readiness(tmp_path)

    assert any(check.name == "Repository identity alignment" and not check.passed for check in report.checks)


def test_release_cli_reports_json_and_nonzero_when_not_ready(tmp_path):
    result = CliRunner().invoke(app, ["release", "check", "--path", str(tmp_path), "--json"])

    assert result.exit_code == 1
    assert json.loads(result.output)["ready"] is False
