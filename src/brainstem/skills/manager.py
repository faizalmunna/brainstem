"""Skill package manager: install/remove third-party skill packs.

Together with state.py's enable/disable, this is the "package manager for
skills" the tool needs to be genuinely extensible rather than a fixed
bundle: brainstem ships strong defaults (skills/packs/), but a user can
install someone else's pack (a local directory or a git repo of skill
.md files) or their own, on top -- without forking brainstem itself.

Deliberately CLI-only, not exposed as an MCP tool: installing a pack can
run arbitrary-content skills and (for git sources) fetches from the
network, which is exactly the kind of action the plan's guardrail
philosophy (Q9) says needs a human in the loop, not an agent deciding to
clone something on its own initiative over an MCP call.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

INSTALLED_DIRNAME = "installed"


def installed_dir(repo_root: Path) -> Path:
    return repo_root / ".brain" / "skills" / INSTALLED_DIRNAME


def _is_git_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "git@")) or source.endswith(".git")


def install_pack(source: str, repo_root: Path, name: str | None = None) -> str:
    """Install a skill pack (a directory of skill .md files) from a local
    path or a git URL into .brain/skills/installed/<name>/. Returns the
    installed pack name. Raises FileExistsError if that name is already
    installed -- never silently overwrites."""
    target_parent = installed_dir(repo_root)
    target_parent.mkdir(parents=True, exist_ok=True)

    if _is_git_url(source):
        pack_name = name or Path(source.rstrip("/").removesuffix(".git")).name
        dest = target_parent / pack_name
        if dest.exists():
            raise FileExistsError(f"Pack '{pack_name}' is already installed at {dest}")
        result = subprocess.run(
            ["git", "clone", "--depth", "1", source, str(dest)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr.strip()}")
        shutil.rmtree(dest / ".git", ignore_errors=True)
        return pack_name

    src_path = Path(source).expanduser().resolve()
    if not src_path.is_dir():
        raise NotADirectoryError(f"{src_path} is not a directory of skill files")
    pack_name = name or src_path.name
    dest = target_parent / pack_name
    if dest.exists():
        raise FileExistsError(f"Pack '{pack_name}' is already installed at {dest}")
    shutil.copytree(src_path, dest, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    return pack_name


def remove_pack(pack_name: str, repo_root: Path) -> None:
    """Remove an installed pack. Only ever touches .brain/skills/installed/
    -- bundled packs and repo-local .brain/skills/*.md files are never
    deletable this way; use SkillState.disable() for those instead."""
    dest = installed_dir(repo_root) / pack_name
    if not dest.exists():
        raise FileNotFoundError(f"No installed pack named '{pack_name}' at {dest}")
    shutil.rmtree(dest)


def list_installed_packs(repo_root: Path) -> list[str]:
    d = installed_dir(repo_root)
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())
