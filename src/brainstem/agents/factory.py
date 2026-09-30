"""Deterministically propose an agent profile from a task description.

Keyword matching is offline and auditable: every granted permission records
the words that produced it. A proposal is never written automatically; a
human must review and explicitly save the resulting permission grant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .permissions import Permission

if TYPE_CHECKING:
    from ..skills.registry import SkillRegistry

# READ is always granted (an agent that can't even read isn't useful).
# Every other permission must be earned by a matching keyword or phrase
# appearing in the task description; multi-word phrases are checked as a
# plain substring since they can't appear as a single tokenized word.
_PERMISSION_KEYWORDS: dict[Permission, set[str]] = {
    Permission.WRITE: {
        "write", "edit", "modify", "update", "create", "generate", "refactor", "implement", "fix",
    },
    Permission.EXECUTE: {"run", "execute", "build", "test", "compile", "verify", "lint"},
    Permission.NETWORK: {
        "fetch", "http", "api", "download", "request", "network", "curl", "webhook",
    },
    Permission.INSTALL: {"install", "dependency", "dependencies", "package", "pip", "npm", "uv"},
    Permission.DATABASE: {"database", "db", "sql", "query", "migration", "schema", "table"},
    Permission.DEPLOY: {"deploy", "release", "publish", "production", "ship"},
    Permission.DELETE: {"delete", "remove", "drop", "purge", "clean up", "cleanup"},
    Permission.SECRET: {"secret", "credential", "credentials", "token", "api key", "password"},
}

_WORD_RE = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


@dataclass(frozen=True, slots=True)
class ProposedAgentProfile:
    name: str
    description: str
    permissions: set[Permission]
    rationale: dict[str, list[str]]  # Permission.value -> matched keywords/phrases
    matched_skills: list[str] = field(default_factory=list)


def slugify(text: str, max_words: int = 4) -> str:
    words = _WORD_RE.findall(text.lower())
    return "-".join(words[:max_words]) or "agent"


def infer_permissions(description: str) -> tuple[set[Permission], dict[str, list[str]]]:
    lowered = description.lower()
    tokens = _words(description)
    granted = {Permission.READ}
    rationale: dict[str, list[str]] = {}
    for permission, keywords in _PERMISSION_KEYWORDS.items():
        hits = sorted(kw for kw in keywords if kw in tokens or kw in lowered)
        if hits:
            granted.add(permission)
            rationale[permission.value] = hits
    return granted, rationale


def propose_profile(
    description: str,
    name: str | None = None,
    registry: "SkillRegistry | None" = None,
) -> ProposedAgentProfile:
    """Build a proposal from a task description. Pass the repo's
    SkillRegistry to also surface skills whose triggers match the same
    description, so a reviewer sees permissions *and* relevant skills for
    the task in one place."""
    permissions, rationale = infer_permissions(description)
    matched_skills: list[str] = []
    if registry is not None:
        matched_skills = sorted({s.name for s in registry.find_by_trigger(description)})
    return ProposedAgentProfile(
        name=name or slugify(description),
        description=description,
        permissions=permissions,
        rationale=rationale,
        matched_skills=matched_skills,
    )
