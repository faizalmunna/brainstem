"""Gitignore-aware file walking, scoped by the manifest's ignore list.

Uses `os.walk` with in-place `dirnames` pruning rather than
`Path.rglob("*")`: rglob has no way to skip descending into a directory
it's about to discard anyway, so it was walking into every ignored
directory in full before filtering -- on this project's own `.venv`
(9,774 files once the `vector`/`providers` extras are installed), that
meant every `brainstem index` call, warm or cold, paid the cost of
stat-ing thousands of irrelevant files. Performance testing caught this
directly: a "warm" reindex (nothing changed) was measured taking as long
as a cold one, which should be structurally impossible if the walk itself
were cheap. Pruning `dirnames` before `os.walk` descends is the standard,
correct fix -- not a fallback path.

The walker deliberately avoids an external binary dependency. `pathspec`
provides the needed gitignore semantics in-process, while directory pruning
removes the dominant cost of ignored trees.
"""

from __future__ import annotations

import os
from pathlib import Path

import pathspec

from ..manifest import BrainManifest
from .parser import LANGUAGE_BY_EXTENSION


def _load_gitignore(repo_root: Path) -> pathspec.PathSpec:
    patterns: list[str] = []
    gitignore = repo_root / ".gitignore"
    if gitignore.exists():
        patterns.extend(gitignore.read_text(encoding="utf-8", errors="ignore").splitlines())
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def iter_source_files(repo_root: Path, manifest: BrainManifest):
    """Yield Path objects for every indexable source file under repo_root.

    Prunes manifest.index.ignore directories and gitignored directories
    before descending into them, so a large ignored directory (.venv,
    node_modules, .git) costs one stat call for the directory itself, not
    one per file inside it.
    """
    repo_root = repo_root.resolve()
    ignore_dirs = set(manifest.index.ignore)
    gitignore_spec = _load_gitignore(repo_root)
    max_bytes = manifest.index.max_file_bytes

    for dirpath, dirnames, filenames in os.walk(repo_root):
        current_dir = Path(dirpath)
        rel_dir = current_dir.relative_to(repo_root)

        def _dir_is_ignored(name: str) -> bool:
            if name in ignore_dirs:
                return True
            rel_posix = (rel_dir / name).as_posix() if rel_dir != Path(".") else name
            return gitignore_spec.match_file(rel_posix + "/")

        dirnames[:] = [d for d in dirnames if not _dir_is_ignored(d)]

        for filename in filenames:
            path = current_dir / filename
            if path.suffix not in LANGUAGE_BY_EXTENSION:
                continue

            rel = path.relative_to(repo_root)
            if gitignore_spec.match_file(rel.as_posix()):
                continue
            try:
                if path.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue

            yield path
