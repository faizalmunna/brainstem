"""Skill package manager for user-approved third-party skill packs.

Installation is deliberately CLI-only: it can download untrusted content and
make it available to later agent sessions. It is never exposed as an MCP tool,
so an agent cannot install a pack on its own initiative.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

INSTALLED_DIRNAME = "installed"
_PACK_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
MAX_PACK_FILES = 10_000
MAX_PACK_BYTES = 64 * 1024 * 1024
_GIT_CLONE_TIMEOUT_S = 60


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
    root = repo_root.resolve()
    target_parent = root
    for component in (".brain", "skills", INSTALLED_DIRNAME):
        candidate = target_parent / component
        # Prove every pre-existing parent is in bounds *before* creating a
        # child. This prevents a `.brain` symlink from redirecting mkdir into
        # an unrelated directory.
        if candidate.exists() or candidate.is_symlink():
            resolved = candidate.resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise ValueError("Refusing skill-pack operation outside the repository .brain directory.") from exc
        else:
            candidate.mkdir()
            resolved = candidate.resolve()
        target_parent = resolved
    return target_parent / _validated_pack_name(pack_name)


def _validate_pack_tree(root: Path) -> None:
    """Reject symlinks/special files and cap extracted third-party content."""
    files = 0
    total_bytes = 0
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                entry_path = Path(entry.path)
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISLNK(mode):
                    raise ValueError(f"Skill packs cannot contain symlinks: {entry_path.name}")
                if stat.S_ISDIR(mode):
                    pending.append(entry_path)
                    continue
                if not stat.S_ISREG(mode):
                    raise ValueError(f"Skill packs cannot contain non-regular files: {entry_path.name}")
                files += 1
                total_bytes += entry.stat(follow_symlinks=False).st_size
                if files > MAX_PACK_FILES or total_bytes > MAX_PACK_BYTES:
                    raise ValueError(
                        f"Skill pack exceeds safety limit of {MAX_PACK_FILES} files or {MAX_PACK_BYTES} bytes."
                    )


def _staging_dir(destination: Path) -> Path:
    return Path(tempfile.mkdtemp(prefix=".brainstem-pack-", dir=destination.parent))


def _commit_staged_pack(staged: Path, destination: Path) -> None:
    _validate_pack_tree(staged)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Pack destination already exists at {destination}")
    # Staging and destination share a parent filesystem, so a rename never
    # exposes a partially copied pack to an agent registry scan.
    staged.rename(destination)


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
        staging = _staging_dir(dest)
        staged_pack = staging / "pack"
        git_env = os.environ.copy()
        # Prevent credentials prompts and ignore arbitrary system/global Git
        # configuration while downloading untrusted pack content.
        git_env["GIT_TERMINAL_PROMPT"] = "0"
        git_env["GIT_CONFIG_NOSYSTEM"] = "1"
        git_env["GIT_CONFIG_GLOBAL"] = os.devnull
        try:
            result = subprocess.run(
                [
                    "git",
                    "-c",
                    "protocol.file.allow=never",
                    "clone",
                    "--depth",
                    "1",
                    "--no-tags",
                    "--",
                    source,
                    str(staged_pack),
                ],
                capture_output=True,
                text=True,
                shell=False,
                timeout=_GIT_CLONE_TIMEOUT_S,
                env=git_env,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone failed: {result.stderr.strip()[:2_000]}")
            shutil.rmtree(staged_pack / ".git", ignore_errors=True)
            _commit_staged_pack(staged_pack, dest)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"git clone timed out after {_GIT_CLONE_TIMEOUT_S} seconds") from exc
        except OSError as exc:
            raise RuntimeError(f"Unable to run git clone: {exc}") from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return pack_name

    src_path = Path(source).expanduser().resolve()
    if not src_path.is_dir():
        raise NotADirectoryError(f"{src_path} is not a directory of skill files")
    pack_name = _validated_pack_name(name if name is not None else src_path.name)
    dest = _destination(repo_root, pack_name)
    if dest.exists():
        raise FileExistsError(f"Pack '{pack_name}' is already installed at {dest}")
    staging = _staging_dir(dest)
    staged_pack = staging / "pack"
    try:
        # Preserve symlinks until validation rather than dereferencing them;
        # dereferencing would allow a local pack to pull arbitrary external
        # files into repository state.
        shutil.copytree(
            src_path,
            staged_pack,
            symlinks=True,
            ignore=shutil.ignore_patterns(".git", "__pycache__"),
        )
        _commit_staged_pack(staged_pack, dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return pack_name


def remove_pack(pack_name: str, repo_root: Path) -> None:
    """Remove an installed pack. Only ever touches .brain/skills/installed/
    -- bundled packs and repo-local .brain/skills/*.md files are never
    deletable this way; use SkillState.disable() for those instead."""
    dest = _destination(repo_root, pack_name)
    if not dest.exists():
        raise FileNotFoundError(f"No installed pack named '{pack_name}' at {dest}")
    if dest.is_symlink():
        raise ValueError(f"Refusing to remove symlinked skill pack: {dest}")
    shutil.rmtree(dest)


def list_installed_packs(repo_root: Path) -> list[str]:
    d = installed_dir(repo_root)
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir() and not p.is_symlink())
