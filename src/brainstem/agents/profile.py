"""Declarative agent profiles with explicit skills and permission grants.

Profiles are loaded from files; the factory can propose one from a task
description, but never persists it without a human decision.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .permissions import Permission

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

AGENTS_DIRNAME = "agents"
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def validate_name(name: str, *, kind: str = "profile") -> str:
    """Reject path-like identifiers before they become filesystem paths."""
    if not _SAFE_NAME.fullmatch(name):
        raise ValueError(
            f"Invalid {kind} name {name!r}; use 1-64 letters, digits, hyphens, or underscores."
        )
    return name


class AgentProfile(BaseModel):
    name: str
    description: str = ""
    permissions: set[Permission] = Field(default_factory=set)
    skills: list[str] = Field(default_factory=list)  # empty = all skills visible
    model_preference: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return validate_name(value)


def full_access_profile() -> AgentProfile:
    return AgentProfile(
        name="full-access",
        description="Unrestricted -- every permission granted. Use only as an explicit, trusted profile.",
        permissions=set(Permission),
    )


def readonly_profile() -> AgentProfile:
    return AgentProfile(
        name="readonly",
        description="Safe default: can inspect repository intelligence but cannot write or execute.",
        permissions={Permission.READ},
    )


def agents_dir(repo_root: Path) -> Path:
    return repo_root / ".brain" / AGENTS_DIRNAME


def load_profile(repo_root: Path, name: str) -> AgentProfile:
    """Load `.brain/agents/<name>.toml`. Raises FileNotFoundError if it
    doesn't exist -- an unrecognized profile name is refused, never
    silently downgraded to full access."""
    name = validate_name(name)
    path = agents_dir(repo_root) / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(
            f"No agent profile named '{name}' at {path}. "
            f"Create it with `brainstem agent create`, or omit --profile for the safe read-only default."
        )
    with path.open("rb") as f:
        data = tomllib.load(f)
    data.setdefault("name", name)
    return AgentProfile.model_validate(data)


def save_profile(repo_root: Path, profile: AgentProfile) -> Path:
    validate_name(profile.name)
    path = agents_dir(repo_root) / f"{profile.name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    perms = ", ".join(json.dumps(p.value) for p in sorted(profile.permissions, key=lambda p: p.value))
    skills = ", ".join(json.dumps(s) for s in profile.skills)
    lines = [
        f"name = {json.dumps(profile.name)}",
        f"description = {json.dumps(profile.description)}",
        f"permissions = [{perms}]",
        f"skills = [{skills}]",
    ]
    if profile.model_preference:
        lines.append(f"model_preference = {json.dumps(profile.model_preference)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
