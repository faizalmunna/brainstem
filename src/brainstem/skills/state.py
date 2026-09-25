"""Per-repo enable/disable state -- the toggle half of the package-manager
model: ship strong defaults, but let a user turn off any single skill
(bundled, repo-local, or installed) without deleting or forking files.

Stored separately from the skill files themselves specifically so
disabling a *bundled* skill (one that lives inside the installed
`brainstem` package, not the target repo) never requires editing a file
outside the repo -- the repo's `.brain/skills/state.json` is the only
thing that changes.
"""

from __future__ import annotations

import json
from pathlib import Path

from .._atomic import atomic_write_text


def state_path(repo_root: Path) -> Path:
    return repo_root / ".brain" / "skills" / "state.json"


class SkillState:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._disabled: set[str] = set()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self._disabled = set(data.get("disabled", []))

    def is_enabled(self, name: str) -> bool:
        return name not in self._disabled

    def disable(self, name: str) -> None:
        self._disabled.add(name)
        self._save()

    def enable(self, name: str) -> None:
        self._disabled.discard(name)
        self._save()

    def list_disabled(self) -> list[str]:
        return sorted(self._disabled)

    def _save(self) -> None:
        atomic_write_text(self._path, json.dumps({"disabled": sorted(self._disabled)}, indent=2))
