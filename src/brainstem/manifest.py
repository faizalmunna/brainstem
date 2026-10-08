"""brain.toml manifest schema and loader.

The manifest is the portable config that lives at the root of a target
repo's .brain/ directory. It declares indexing scope, memory backend choice,
and model routing preferences without binding the repo to any specific vendor
SDK.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ._atomic import atomic_write_text

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

MANIFEST_FILENAME = "brain.toml"
BRAIN_DIR = ".brain"

DEFAULT_IGNORE = [
    ".git",
    ".brain",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "target",
    ".next",
    ".turbo",
    # Benchmarks and local packaging checks commonly emit disposable evidence
    # here; never make that generated material part of a repository graph.
    ".tmp",
]


class IndexConfig(BaseModel):
    ignore: list[str] = Field(default_factory=lambda: list(DEFAULT_IGNORE))
    # A manifest is repository-controlled input. Keep its per-file read cap
    # bounded even when a malformed or overly broad config is supplied.
    max_file_bytes: int = Field(default=1_000_000, ge=1, le=50_000_000)


class MemoryConfig(BaseModel):
    # The embedded SQLite backend is the default; adapters may add others.
    backend: str = "sqlite"


class ModelConfig(BaseModel):
    default_provider: str = "anthropic"
    local_fallback: str = "ollama"
    fallback_providers: list[str] = Field(default_factory=lambda: ["openai", "ollama"])
    anthropic_model: str = "claude-sonnet-4-5"
    openai_model: str = "gpt-4.1-mini"
    local_model: str = "llama3.2"
    # Enforced before a remote request and translated to each provider's
    # native output-limit parameter by its adapter.
    max_input_tokens: int = Field(default=16_000, ge=1, le=1_000_000)
    max_output_tokens: int = Field(default=1_024, ge=1, le=100_000)
    embedding_model: str = "nomic-embed-text-v1.5"

    @field_validator("default_provider", "local_fallback")
    @classmethod
    def known_provider(cls, value: str) -> str:
        if value not in {"anthropic", "openai", "ollama"}:
            raise ValueError("model providers must be one of: anthropic, openai, ollama.")
        return value

    @field_validator("fallback_providers")
    @classmethod
    def known_fallback_providers(cls, value: list[str]) -> list[str]:
        if any(provider not in {"anthropic", "openai", "ollama"} for provider in value):
            raise ValueError("model fallback_providers must use: anthropic, openai, ollama.")
        return list(dict.fromkeys(value))


class ProjectConfig(BaseModel):
    name: str = "unnamed-project"


class VerifyConfig(BaseModel):
    # Empty = not configured; verify.detect_commands() supplies a
    # best-effort default at call time rather than baking a guess into
    # every freshly-init'd manifest.
    commands: list[str] = Field(default_factory=list)
    timeout_s: int = 300
    # Native is retained for compatibility. A production/high-risk repo can
    # opt into docker, which fails closed when its prebuilt image/daemon is
    # unavailable rather than running verification on the host instead.
    runner: Literal["native", "docker"] = "native"
    docker_image: str = ""


class BrainManifest(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    index: IndexConfig = Field(default_factory=IndexConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    verify: VerifyConfig = Field(default_factory=VerifyConfig)


def brain_dir(repo_root: Path) -> Path:
    """Return the local state directory without following it outside a repo.

    `.brain` is written by many subsystems (memory, workflows, audit, skills,
    and graph storage). Making the boundary check central prevents a malicious
    or accidental symlink from turning any of those normal writes into a write
    elsewhere on the machine.
    """
    root = repo_root.resolve()
    candidate = root / BRAIN_DIR
    if candidate.exists() or candidate.is_symlink():
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Refusing .brain state directory outside repository: {candidate}") from exc
        if not resolved.is_dir():
            raise ValueError(f"Brainstem state path is not a directory: {candidate}")
        return resolved
    return candidate


def manifest_path(repo_root: Path) -> Path:
    return brain_state_path(repo_root, MANIFEST_FILENAME)


def brain_state_path(repo_root: Path, *parts: str) -> Path:
    """Resolve a named `.brain` state path while preserving workspace bounds.

    Each existing component is checked before the next component is created.
    That closes the otherwise subtle case where `.brain/audit` or
    `.brain/index` is itself a symlink outside the selected repository.
    Callers provide only fixed internal component names, never user paths.
    """
    root = repo_root.resolve()
    current = brain_dir(root)
    for index, part in enumerate(parts):
        component = Path(part)
        if not part or component.is_absolute() or len(component.parts) != 1 or part in {".", ".."}:
            raise ValueError("Brainstem state path components must be single, relative names.")
        candidate = current / component
        if candidate.exists() or candidate.is_symlink():
            resolved = candidate.resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Refusing .brain state path outside repository: {candidate}") from exc
            if index < len(parts) - 1 and not resolved.is_dir():
                raise ValueError(f"Brainstem state parent is not a directory: {candidate}")
            current = resolved
        else:
            current = candidate
    return current


def default_manifest(project_name: str) -> BrainManifest:
    return BrainManifest(project=ProjectConfig(name=project_name))


def load_manifest(repo_root: Path) -> BrainManifest:
    path = manifest_path(repo_root)
    if not path.exists():
        raise FileNotFoundError(
            f"No {MANIFEST_FILENAME} found at {path}. Run `brainstem init` first."
        )
    with path.open("rb") as f:
        data = tomllib.load(f)
    return BrainManifest.model_validate(data)


def save_manifest(repo_root: Path, manifest: BrainManifest) -> Path:
    path = manifest_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "[project]",
        f"name = {_toml_string(manifest.project.name)}",
        "",
        "[index]",
        f"ignore = {_toml_string_list(manifest.index.ignore)}",
        f"max_file_bytes = {manifest.index.max_file_bytes}",
        "",
        "[memory]",
        f"backend = {_toml_string(manifest.memory.backend)}",
        "",
        "[model]",
        f"default_provider = {_toml_string(manifest.model.default_provider)}",
        f"local_fallback = {_toml_string(manifest.model.local_fallback)}",
        f"fallback_providers = {_toml_string_list(manifest.model.fallback_providers)}",
        f"anthropic_model = {_toml_string(manifest.model.anthropic_model)}",
        f"openai_model = {_toml_string(manifest.model.openai_model)}",
        f"local_model = {_toml_string(manifest.model.local_model)}",
        f"max_input_tokens = {manifest.model.max_input_tokens}",
        f"max_output_tokens = {manifest.model.max_output_tokens}",
        f"embedding_model = {_toml_string(manifest.model.embedding_model)}",
        "",
        "[verify]",
        f"commands = {_toml_string_list(manifest.verify.commands)}",
        f"timeout_s = {manifest.verify.timeout_s}",
        f"runner = {_toml_string(manifest.verify.runner)}",
        f"docker_image = {_toml_string(manifest.verify.docker_image)}",
        "",
    ]
    return atomic_write_text(path, "\n".join(lines))


def _toml_string(value: str) -> str:
    """Encode a TOML basic string without allowing a value to alter config."""
    # TOML basic strings deliberately accept the JSON string escape grammar.
    return json.dumps(value, ensure_ascii=False)


def _toml_string_list(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"
