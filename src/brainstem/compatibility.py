"""Safe inspection and enablement of external workflow skill packs.

Compatibility is metadata-only. Brainstem never executes third-party hooks,
copies a pack, or fetches from a network URL merely because a user inspected
it. Explicit enablement records a local pointer and the license acceptance.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._atomic import atomic_write_text
from .manifest import brain_state_path

SUPPORTED_CAPABILITIES = {"mcp", "session-start", "workflow", "approval", "skills"}
ENABLED_FILENAME = "compatibility/enabled.json"


class WorkflowPackV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    pack_id: str = Field(min_length=1, max_length=128)
    version: str = Field(default="unknown", max_length=128)
    license: str = Field(default="unknown", max_length=256)
    triggers: list[str] = Field(default_factory=list, max_length=64)
    required_permissions: list[str] = Field(default_factory=list, max_length=32)
    supported_capabilities: list[str] = Field(default_factory=list, max_length=16)
    artifact_mapping: dict[str, str] = Field(default_factory=dict, max_length=32)
    source_path: str
    compatible: bool = True
    notes: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("triggers", "required_permissions", "supported_capabilities", "notes")
    @classmethod
    def bounded_entries(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > 1_000 for item in normalized):
            raise ValueError("Workflow-pack entries must be non-empty and at most 1000 characters.")
        return normalized

    @field_validator("supported_capabilities")
    @classmethod
    def known_capabilities(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - SUPPORTED_CAPABILITIES)
        if unknown:
            raise ValueError(f"Unsupported workflow-pack capabilities: {', '.join(unknown)}")
        return sorted(set(value))


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def inspect_pack(source: Path) -> WorkflowPackV1:
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Workflow pack directory does not exist: {source}")
    declared = _read_json(source / "brainstem.workflow.json")
    if declared:
        # This is Brainstem's explicit exchange contract. It stays data-only:
        # hooks, scripts, URLs, and unknown metadata never get executed here.
        return WorkflowPackV1.model_validate({**declared, "source_path": str(source)})
    plugin = _read_json(source / "plugin.json")
    if not plugin:
        plugin = _read_json(source / ".codex-plugin" / "plugin.json")
    package = _read_json(source / "package.json")
    metadata = plugin or package
    pack_id = str(metadata.get("name") or source.name).strip()
    license_name = str(metadata.get("license") or "unknown").strip()
    skills_value = metadata.get("skills", [])
    triggers: list[str] = []
    if isinstance(skills_value, str):
        triggers.append(skills_value)
    elif isinstance(skills_value, list):
        triggers.extend(str(item) for item in skills_value if isinstance(item, str))
    capabilities = ["skills"] if triggers or (source / "skills").is_dir() else []
    if plugin:
        capabilities.append("session-start")
    notes: list[str] = []
    if not metadata:
        notes.append("No plugin.json or package.json found; only a local skill-directory pointer can be enabled.")
    if license_name == "unknown":
        notes.append("License is unknown; review it before enabling this pack.")
    return WorkflowPackV1(
        pack_id=pack_id,
        version=str(metadata.get("version") or "unknown"),
        license=license_name,
        triggers=sorted(set(triggers)),
        required_permissions=[],
        supported_capabilities=sorted(set(capabilities) & SUPPORTED_CAPABILITIES),
        artifact_mapping={"design": "design", "plan": "plan", "test_plan": "test_plan", "review": "review"},
        source_path=str(source),
        notes=notes,
    )


def enabled_packs_path(repo_root: Path) -> Path:
    return brain_state_path(repo_root, *Path(ENABLED_FILENAME).parts)


def list_enabled_packs(repo_root: Path) -> list[dict]:
    path = enabled_packs_path(repo_root)
    payload = _read_json(path)
    packs = payload.get("packs", [])
    return packs if isinstance(packs, list) else []


def enable_pack(repo_root: Path, pack: WorkflowPackV1, *, accept_license: bool) -> Path:
    if not accept_license:
        raise PermissionError("Enablement requires --accept-license after reviewing the pack metadata and license.")
    path = enabled_packs_path(repo_root)
    entries = [entry for entry in list_enabled_packs(repo_root) if entry.get("pack_id") != pack.pack_id]
    entries.append(
        {
            "pack_id": pack.pack_id,
            "version": pack.version,
            "license": pack.license,
            "source_path": pack.source_path,
            "supported_capabilities": pack.supported_capabilities,
            "license_accepted": True,
        }
    )
    return atomic_write_text(path, json.dumps({"schema_version": 1, "packs": entries}, indent=2, sort_keys=True) + "\n")
