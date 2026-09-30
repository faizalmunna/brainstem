"""Skill registry: loads markdown+YAML-frontmatter skill manifests.

Human-readable, git-diffable, no code execution required to discover
what a skill does. Skills are pure data -- adding a capability means
adding a file, never touching core code or the MCP server's
tool-dispatch logic.

Skills are organized into **packs** -- a pack is a directory under
`<root>/packs/<name>/` or `<root>/installed/<name>/`.

Enable/disable (state.py) is the other half of the package-manager model:
`list()`/`find_by_trigger()` hide disabled skills by default so a user
can turn off any single skill -- bundled, repo-local, or installed --
without deleting or forking a file. `get()` stays unfiltered, since
`brainstem skill enable/disable` needs to look up a skill by name to
validate it exists regardless of its current state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .state import SkillState

try:
    _YAML_LOADER = yaml.CSafeLoader  # libyaml (C) -- ~8x faster than pure-Python SafeLoader
except AttributeError:
    _YAML_LOADER = yaml.SafeLoader  # falls back where libyaml isn't installed

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

GENERAL_PACK = "general"
_PACK_ROOTS = ("packs", "installed")
MAX_SKILL_FILE_BYTES = 256 * 1024
MAX_SKILL_DESCRIPTION_CHARS = 2_000
MAX_SKILL_TRIGGERS = 32
MAX_SKILL_TRIGGER_CHARS = 256
MAX_SKILL_PERMISSIONS = 32


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    triggers: list[str]
    permissions: list[str]
    body: str
    source_path: str
    pack: str = GENERAL_PACK


def _pack_name(md_path: Path, root: Path) -> str:
    """A skill under `<root>/packs/<name>/...` or `<root>/installed/<name>/...`
    belongs to `<name>`; anything else (loose files directly in `<root>`)
    is GENERAL_PACK."""
    try:
        rel_parts = md_path.relative_to(root).parts
    except ValueError:
        return GENERAL_PACK
    if len(rel_parts) >= 2 and rel_parts[0] in _PACK_ROOTS:
        return rel_parts[1]
    return GENERAL_PACK


def _parse_skill_file(path: Path, pack: str) -> Skill | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SKILL_FILE_BYTES:
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    front_raw, body = match.groups()
    # _YAML_LOADER is always SafeLoader or CSafeLoader; never accept Python
    # object constructors from an installed skill manifest.
    front = yaml.load(front_raw, Loader=_YAML_LOADER) or {}  # nosec B506
    if not isinstance(front, dict) or "name" not in front:
        return None
    name = front["name"]
    description = front.get("description", "")
    triggers = front.get("triggers", [])
    permissions = front.get("permissions", [])
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 128
        or not isinstance(description, str)
        or len(description) > MAX_SKILL_DESCRIPTION_CHARS
        or not isinstance(triggers, list)
        or len(triggers) > MAX_SKILL_TRIGGERS
        or any(not isinstance(item, str) or len(item) > MAX_SKILL_TRIGGER_CHARS for item in triggers)
        or not isinstance(permissions, list)
        or len(permissions) > MAX_SKILL_PERMISSIONS
        or any(not isinstance(item, str) or len(item) > 64 for item in permissions)
    ):
        return None
    return Skill(
        name=name,
        description=description,
        triggers=triggers,
        permissions=permissions,
        body=body.strip(),
        source_path=str(path),
        pack=pack,
    )


class SkillRegistry:
    def __init__(self, directories: list[Path], state: SkillState | None = None) -> None:
        self._skills: dict[str, Skill] = {}
        self._state = state
        for directory in directories:
            if not directory.is_dir():
                continue
            try:
                root = directory.resolve(strict=True)
            except OSError:
                continue
            for md_path in sorted(directory.rglob("*.md")):
                if md_path.name.upper().startswith("README"):
                    continue
                try:
                    if md_path.is_symlink() or not md_path.is_file():
                        continue
                    md_path.resolve(strict=True).relative_to(root)
                except (OSError, ValueError):
                    continue
                skill = _parse_skill_file(md_path, _pack_name(md_path, directory))
                if skill is not None:
                    self._skills[skill.name] = skill  # later dirs override earlier ones

    def _enabled(self, skill: Skill) -> bool:
        return self._state is None or self._state.is_enabled(skill.name)

    def list(self, pack: str | None = None, include_disabled: bool = False) -> list[Skill]:
        skills = self._skills.values()
        if pack is not None:
            skills = (s for s in skills if s.pack == pack)
        if not include_disabled:
            skills = (s for s in skills if self._enabled(s))
        return sorted(skills, key=lambda s: (s.pack, s.name))

    def list_packs(self) -> list[str]:
        return sorted({s.pack for s in self._skills.values()})

    def get(self, name: str) -> Skill | None:
        """Unfiltered by enabled state -- used to validate a name exists
        before enabling/disabling/removing it."""
        return self._skills.get(name)

    def is_enabled(self, name: str) -> bool:
        return self._state is None or self._state.is_enabled(name)

    def find_by_trigger(self, text: str) -> list[Skill]:
        needle = text.lower()
        return [
            skill
            for skill in self._skills.values()
            if self._enabled(skill) and any(trigger.lower() in needle for trigger in skill.triggers)
        ]
