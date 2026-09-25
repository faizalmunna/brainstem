"""Skill package manager for user-approved third-party skill packs.

Installation is deliberately CLI-only: it can download untrusted content and
make it available to later agent sessions. It is never exposed as an MCP tool,
so an agent cannot install a pack on its own initiative.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

INSTALLED_DIRNAME = "installed"
_PACK_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def installed_dir(repo_root: Path) -> Path:
    return repo_root / ".brain" / "skills" / INSTALLED_DIRNAME


def _is_git_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "git@")) or source.endswith(".git")


def _validated_pack_name(name: str) -> str:
    """Return a portable one-segment pack name or fail before touching disk."""
    if not isinstance(name, str) or not _PACK_NAME_RE.fullmatch(name):
        raise ValueError(
            "pack name must be 1-64 ASCII letters, digits, '.', '_' or '-', "
            "start with a letter or digit, and contain no path separators"
        )
    return name


def _destination(repo_root: Path, pack_name: str) -> Path:
    """Build an installed-pack path after enforcing a non-escaping name."""
    target_parent = installed_dir(repo_root)
    target_parent.mkdir(parents=True, exist_ok=True)
    return target_parent / _validated_pack_name(pack_name)


def install_pack(source: str, repo_root: Path, name: str | None = None) -> str:
    """Install a skill pack (a directory of skill .md files) from a local
    path or a git URL into .brain/skills/installed/<name>/. Returns the
    installed pack name. Raises FileExistsError if that name is already
    installed -- never silently overwrites."""
    if _is_git_url(source):
        pack_name = _validated_pack_name(
            name if name is not None else Path(source.rstrip("/").removesuffix(".git")).name
        )
        dest = _destination(repo_root, pack_name)
        if dest.exists():
            raise FileExistsError(f"Pack '{pack_name}' is already installed at {dest}")
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--", source, str(dest)],
            capture_output=True,
            text=True,
            shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr.strip()}")
        shutil.rmtree(dest / ".git", ignore_errors=True)
        return pack_name

    src_path = Path(source).expanduser().resolve()
    if not src_path.is_dir():
        raise NotADirectoryError(f"{src_path} is not a directory of skill files")
    pack_name = _validated_pack_name(name if name is not None else src_path.name)
    dest = _destination(repo_root, pack_name)
    if dest.exists():
        raise FileExistsError(f"Pack '{pack_name}' is already installed at {dest}")
    shutil.copytree(src_path, dest, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    return pack_name


def remove_pack(pack_name: str, repo_root: Path) -> None:
    """Remove an installed pack. Only ever touches .brain/skills/installed/
    -- bundled packs and repo-local .brain/skills/*.md files are never
    deletable this way; use SkillState.disable() for those instead."""
    dest = _destination(repo_root, pack_name)
    if not dest.exists():
        raise FileNotFoundError(f"No installed pack named '{pack_name}' at {dest}")
    shutil.rmtree(dest)


def list_installed_packs(repo_root: Path) -> list[str]:
    d = installed_dir(repo_root)
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())
