"""Independent agent-team composition and least-privilege role routing.

A team defines the agent identity allowed to act at each workflow state.
Connected hosts may orchestrate the team with their own subagent facility;
Brainstem can also run one bounded provider-backed turn at a time through
``agents.runtime``. Neither route grants an agent more than its saved profile
and workflow scope.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .._atomic import atomic_write_text
from ..manifest import brain_state_path
from .permissions import Permission
from .profile import AgentProfile, load_profile, save_profile, validate_name

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

TEAMS_DIRNAME = "teams"
DEFAULT_DELIVERY_TEAM = "delivery"

# A useful team is more than role names in a README. These profiles are a
# conservative starting point: only the worker expected to change source is
# granted WRITE, and only the tester receives EXECUTE. A host or the bounded
# local agent runtime may run roles independently.
DELIVERY_BLUEPRINT: tuple[tuple[str, str, set[Permission]], ...] = (
    ("explorer", "Retrieve bounded repository evidence and map dependencies.", {Permission.READ}),
    ("designer", "Record architecture choices and trade-offs for review.", {Permission.READ}),
    ("planner", "Turn approved design into small, verifiable work items.", {Permission.READ}),
    ("implementer", "Make one bounded source change from an approved plan.", {Permission.READ, Permission.WRITE}),
    ("tester", "Run configured verification and attach executed evidence.", {Permission.READ, Permission.EXECUTE}),
    ("reviewer", "Independently review the plan, change, and evidence.", {Permission.READ}),
    ("coordinator", "Route only the next workflow item whose prerequisites are met.", {Permission.READ}),
)


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
    return brain_state_path(repo_root, "agents", TEAMS_DIRNAME)


def save_team(repo_root: Path, team: AgentTeam, *, validate_profiles: bool = True) -> Path:
    """Raises FileNotFoundError if a member references a profile that
    doesn't exist -- a team pointing at nothing isn't useful to a host,
    and catching it at creation time is better than a host discovering
    it later."""
    validate_name(team.name, kind="team")
    if validate_profiles:
        for member in team.members:
            load_profile(repo_root, member.profile)

    path = brain_state_path(repo_root, "agents", TEAMS_DIRNAME, f"{team.name}.toml")
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
    path = brain_state_path(repo_root, "agents", TEAMS_DIRNAME, f"{name}.toml")
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
    path = brain_state_path(repo_root, "agents", TEAMS_DIRNAME, f"{name}.toml")
    if not path.exists():
        raise FileNotFoundError(f"No team named '{name}' at {path}.")
    path.unlink()


def delivery_team_preview() -> AgentTeam:
    """Return the standard seven-role team without modifying repository state."""
    return AgentTeam(
        name=DEFAULT_DELIVERY_TEAM,
        description="Independent, least-privilege delivery roles for a host-managed engineering workflow.",
        members=[TeamMember(profile=name, role=name) for name, _, _ in DELIVERY_BLUEPRINT],
    )


def bootstrap_delivery_team(repo_root: Path, *, replace: bool = False) -> Path:
    """Persist the standard team only after an explicit caller decision.

    Existing profiles and teams are never overwritten implicitly. The helper
    writes individual profile files first so ``save_team`` can validate every
    reference before returning a usable team path.
    """
    preview = delivery_team_preview()
    team_path = brain_state_path(repo_root, "agents", TEAMS_DIRNAME, f"{preview.name}.toml")
    profile_paths = [brain_state_path(repo_root, "agents", f"{name}.toml") for name, _, _ in DELIVERY_BLUEPRINT]
    existing = [path for path in [team_path, *profile_paths] if path.exists()]
    if existing and not replace:
        names = ", ".join(str(path.relative_to(repo_root)) for path in existing)
        raise FileExistsError(f"Refusing to overwrite existing delivery-team state: {names}. Rerun with replace=True.")
    for name, description, permissions in DELIVERY_BLUEPRINT:
        save_profile(repo_root, AgentProfile(name=name, description=description, permissions=permissions))
    return save_team(repo_root, preview)
