"""Declarative agent-team composition: a named set of {profile, role}
pairs that a host agent (Claude Code's own subagent system, Codex's,
etc.) queries and uses to spawn its own multi-agent execution -- brainstem
defines the WHO and WHAT PERMISSIONS, the host still does the actual
multi-agent orchestration and LLM calls.

Brainstem is a coordination layer, not another agent runner. An actual
multi-agent execution engine would duplicate host behavior and add another
agent loop. A team is therefore declarative data a host can consume, never
something Brainstem executes itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .._atomic import atomic_write_text
from .profile import agents_dir, load_profile, validate_name

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

TEAMS_DIRNAME = "teams"


class TeamMember(BaseModel):
    profile: str  # references a saved AgentProfile by name
    role: str  # free-form label, e.g. "planner", "implementer", "reviewer"


class AgentTeam(BaseModel):
    name: str
    description: str = ""
    members: list[TeamMember] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return validate_name(value, kind="team")


def teams_dir(repo_root: Path) -> Path:
    return agents_dir(repo_root) / TEAMS_DIRNAME


def save_team(repo_root: Path, team: AgentTeam, *, validate_profiles: bool = True) -> Path:
    """Raises FileNotFoundError if a member references a profile that
    doesn't exist -- a team pointing at nothing isn't useful to a host,
    and catching it at creation time is better than a host discovering
    it later."""
    validate_name(team.name, kind="team")
    if validate_profiles:
        for member in team.members:
            load_profile(repo_root, member.profile)

    path = teams_dir(repo_root) / f"{team.name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"name = {json.dumps(team.name)}", f"description = {json.dumps(team.description)}", ""]
    for member in team.members:
        lines.append("[[members]]")
        lines.append(f"profile = {json.dumps(member.profile)}")
        lines.append(f"role = {json.dumps(member.role)}")
        lines.append("")
    return atomic_write_text(path, "\n".join(lines))


def load_team(repo_root: Path, name: str) -> AgentTeam:
    name = validate_name(name, kind="team")
    path = teams_dir(repo_root) / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No team named '{name}' at {path}.")
    with path.open("rb") as f:
        data = tomllib.load(f)
    data.setdefault("name", name)
    return AgentTeam.model_validate(data)


def list_teams(repo_root: Path) -> list[str]:
    d = teams_dir(repo_root)
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.toml"))


def remove_team(repo_root: Path, name: str) -> None:
    name = validate_name(name, kind="team")
    path = teams_dir(repo_root) / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No team named '{name}' at {path}.")
    path.unlink()
