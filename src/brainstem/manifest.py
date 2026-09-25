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

from pydantic import BaseModel, Field

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
]


class IndexConfig(BaseModel):
    ignore: list[str] = Field(default_factory=lambda: list(DEFAULT_IGNORE))
    max_file_bytes: int = 1_000_000


class MemoryConfig(BaseModel):
    # The embedded SQLite backend is the default; adapters may add others.
    backend: str = "sqlite"


class ModelConfig(BaseModel):
    default_provider: str = "anthropic"
    local_fallback: str = "ollama"
    embedding_model: str = "nomic-embed-text-v1.5"


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
    return repo_root / BRAIN_DIR


def manifest_path(repo_root: Path) -> Path:
    return brain_dir(repo_root) / MANIFEST_FILENAME


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
        f"embedding_model = {_toml_string(manifest.model.embedding_model)}",
        "",
        "[verify]",
        f"commands = {_toml_string_list(manifest.verify.commands)}",
        f"timeout_s = {manifest.verify.timeout_s}",
        f"runner = {_toml_string(manifest.verify.runner)}",
        f"docker_image = {_toml_string(manifest.verify.docker_image)}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _toml_string(value: str) -> str:
    """Encode a TOML basic string without allowing a value to alter config."""
    # TOML basic strings deliberately accept the JSON string escape grammar.
    return json.dumps(value, ensure_ascii=False)


def _toml_string_list(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"
