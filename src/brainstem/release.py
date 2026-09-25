"""Read-only release-readiness checks for Brainstem's own source repository.

This is intentionally not a publisher. Publishing needs a maintainer-owned
registry identity and credentials; this module makes every prerequisite
visible without guessing either of them or mutating a checkout.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReleaseCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ReleaseReport:
    repo_root: str
    checks: list[ReleaseCheck]

    @property
    def ready(self) -> bool:
        return all(check.passed for check in self.checks)

    def as_dict(self) -> dict:
        return {
            "ready": self.ready,
            "repo_root": self.repo_root,
            "checks": [asdict(check) for check in self.checks],
        }


def _git(repo_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as file:
            parsed = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _load_json(path: Path) -> dict:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _repository_url(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict) and isinstance(value.get("url"), str):
        return value["url"].strip()
    return ""


def _repository_identity(url: str) -> str:
    """Normalize common Git/HTTPS spellings only for equality checks."""
    value = url.strip().removesuffix("/").removesuffix(".git")
    if value.startswith("git@") and ":" in value:
        host_and_path = value.removeprefix("git@").replace(":", "/", 1)
        return host_and_path.lower()
    value = re.sub(r"^[a-z][a-z0-9+.-]*://", "", value, flags=re.IGNORECASE)
    return value.lower()


def release_readiness(repo_root: Path) -> ReleaseReport:
    """Assess source-controlled prerequisites for a public production release."""
    root = repo_root.resolve()
    pyproject_path = root / "pyproject.toml"
    npm_path = root / "npm" / "package.json"
    security_path = root / "SECURITY.md"
    ci_path = root / ".github" / "workflows" / "ci.yml"
    codeql_path = root / ".github" / "workflows" / "codeql.yml"
    release_workflow_path = root / ".github" / "workflows" / "release-artifacts.yml"
    pyproject = _load_toml(pyproject_path)
    package = _load_json(npm_path)
    project = pyproject.get("project") if isinstance(pyproject.get("project"), dict) else {}
    urls = project.get("urls") if isinstance(project.get("urls"), dict) else {}
    py_version = project.get("version") if isinstance(project.get("version"), str) else ""
    npm_version = package.get("version") if isinstance(package.get("version"), str) else ""
    python_repository = _repository_url(urls.get("Repository"))
    npm_repository = _repository_url(package.get("repository"))
    origin = _git(root, "remote", "get-url", "origin")
    status = _git(root, "status", "--porcelain=v1")
    security = security_path.read_text(encoding="utf-8", errors="replace") if security_path.exists() else ""
    ci = ci_path.read_text(encoding="utf-8", errors="replace") if ci_path.exists() else ""
    codeql = codeql_path.read_text(encoding="utf-8", errors="replace") if codeql_path.exists() else ""
    release_workflow = release_workflow_path.read_text(encoding="utf-8", errors="replace") if release_workflow_path.exists() else ""
    tag_gated_release = all(
        marker in ci
        for marker in (
            "startsWith(github.ref, 'refs/tags/v')",
            "needs: [security, python, npm-wrapper, docker-image]",
            "uses: ./.github/workflows/release-artifacts.yml",
        )
    ) and "workflow_call:" in release_workflow
    cross_architecture_ci = all(
        marker in ci
        for marker in (
            "docker/setup-qemu-action@v3",
            "--platform linux/arm64",
            "MCP_TEST_TIMEOUT_S=60",
        )
    )

    checks = [
        ReleaseCheck(
            "Python distribution metadata",
            bool(project.get("name") and py_version),
            f"{project.get('name', 'missing')} {py_version or '(missing version)'}",
        ),
        ReleaseCheck(
            "npm wrapper version alignment",
            bool(py_version and npm_version and py_version == npm_version),
            f"Python={py_version or '(missing)'}, npm={npm_version or '(missing)'}",
        ),
        ReleaseCheck("Locked dependency graph", (root / "uv.lock").is_file(), "uv.lock is required for verified installs"),
        ReleaseCheck("License", (root / "LICENSE").is_file(), "MIT license file is present"),
        ReleaseCheck(
            "Python repository metadata",
            bool(python_repository),
            python_repository or "Set [project.urls].Repository to the verified repository URL",
        ),
        ReleaseCheck(
            "npm repository metadata",
            bool(npm_repository),
            npm_repository or "Set npm/package.json repository to the same verified repository URL",
        ),
        ReleaseCheck(
            "Git origin remote",
            bool(origin),
            origin or "Configure origin before publishing; no URL is guessed by Brainstem",
        ),
        ReleaseCheck(
            "Repository identity alignment",
            bool(python_repository and npm_repository and origin)
            and len({_repository_identity(python_repository), _repository_identity(npm_repository), _repository_identity(origin)})
            == 1,
            "Python, npm, and origin identify the same repository"
            if python_repository and npm_repository and origin
            and len({_repository_identity(python_repository), _repository_identity(npm_repository), _repository_identity(origin)}) == 1
            else "Set matching verified repository URLs in Python metadata, npm metadata, and origin",
        ),
        ReleaseCheck(
            "Security reporting channel",
            bool(security) and "no verified public remote yet" not in security.lower(),
            "Configured" if security and "no verified public remote yet" not in security.lower() else "Add the real advisory URL and monitored reporting contact to SECURITY.md",
        ),
        ReleaseCheck(
            "Cross-platform CI configuration",
            all(os_name in ci for os_name in ("ubuntu-latest", "macos-latest", "windows-latest"))
            and "npm install" in ci,
            "Windows/Linux/macOS Python and npm install matrix is configured" if ci else "Missing .github/workflows/ci.yml",
        ),
        ReleaseCheck(
            "SBOM generation in CI",
            (root / "src" / "brainstem" / "sbom.py").is_file() and "brainstem sbom" in ci,
            "Locked-runtime SBOM is generated and retained by CI"
            if (root / "src" / "brainstem" / "sbom.py").is_file() and "brainstem sbom" in ci
            else "Add the deterministic SBOM generator and CI artifact step",
        ),
        ReleaseCheck(
            "Code scanning configuration",
            all(
                marker in codeql
                for marker in (
                    "github/codeql-action/init@v4",
                    "github/codeql-action/analyze@v4",
                    "security-events: write",
                    "python",
                    "javascript-typescript",
                )
            ),
            "CodeQL scans the Python runtime and npm wrapper"
            if codeql
            else "Add CodeQL scanning for the Python runtime and npm wrapper",
        ),
        ReleaseCheck(
            "Signed release-artifact workflow",
            all(
                marker in release_workflow
                for marker in ("id-token: write", "attestations: write", "actions/attest@v4", "subject-path", "sbom-path")
            ),
            "Release artifacts receive provenance and SBOM attestations"
            if release_workflow
            else "Add a release workflow with GitHub artifact attestation permissions",
        ),
        ReleaseCheck(
            "Tag-gated cross-platform release",
            tag_gated_release,
            "Release artifact creation waits for the full CI matrix on version tags"
            if tag_gated_release
            else "Make the tag release job depend on security, Windows/Linux/macOS, npm, and Docker checks",
        ),
        ReleaseCheck(
            "Cross-architecture Docker configuration",
            cross_architecture_ci,
            "Linux x86_64 and ARM64 portability/npm tests are configured"
            if cross_architecture_ci
            else "Add ARM64 runtime and npm smoke tests with QEMU to CI",
        ),
        ReleaseCheck(
            "Clean Git worktree",
            status == "",
            "Clean" if status == "" else "Commit or intentionally isolate all changes before a release",
        ),
        ReleaseCheck("Supported Python", sys.version_info >= (3, 11), f"Running Python {sys.version.split()[0]}"),
    ]
    return ReleaseReport(repo_root=str(root), checks=checks)
