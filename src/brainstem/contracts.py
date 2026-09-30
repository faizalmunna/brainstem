"""Versioned, host-neutral contracts used at Brainstem boundaries.

These models deliberately contain evidence and limits rather than prompts or
provider-specific messages.  A coding host can render them however it wants,
but it cannot mistake an inference for a source-backed fact.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .agents.permissions import Permission

MAX_SERIALIZED_CONTRACT_CHARS = 12_000


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class GoalSpecV1(BaseModel):
    """A bounded, reviewable outcome before a workflow is started."""

    schema_version: Literal[1] = 1
    goal: str = Field(min_length=1, max_length=4_000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=32)
    constraints: list[str] = Field(default_factory=list, max_length=32)
    risk: Literal["fast", "standard", "high-risk"] = "standard"
    context_budget_chars: int = Field(default=12_000, ge=1_000, le=100_000)
    allowed_capabilities: list[Permission] = Field(default_factory=lambda: [Permission.READ], max_length=16)

    @field_validator("acceptance_criteria", "constraints")
    @classmethod
    def nonempty_entries(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("Contract list entries cannot be empty.")
        if any(len(item) > 1_000 for item in normalized):
            raise ValueError("Contract list entries cannot exceed 1000 characters.")
        return normalized

    @field_validator("allowed_capabilities")
    @classmethod
    def unique_capabilities(cls, value: list[Permission]) -> list[Permission]:
        if not value:
            raise ValueError("Goal contract must grant at least one capability.")
        if len(set(value)) != len(value):
            raise ValueError("Goal contract capabilities must not be duplicated.")
        return value

    @model_validator(mode="after")
    def artifact_sized(self) -> "GoalSpecV1":
        if len(self.model_dump_json(exclude_none=True)) > MAX_SERIALIZED_CONTRACT_CHARS:
            raise ValueError("Goal contract is too large to persist as bounded workflow evidence.")
        return self


class SourceLocationV1(BaseModel):
    path: str = Field(min_length=1, max_length=4_096)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_hash: str = Field(min_length=32, max_length=128)

    @field_validator("content_hash")
    @classmethod
    def sha256_hash(cls, value: str) -> str:
        value = value.lower()
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("content_hash must be a SHA-256 hexadecimal digest.")
        return value

    @model_validator(mode="after")
    def valid_line_range(self) -> "SourceLocationV1":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line.")
        return self


class CodeFactsV1(BaseModel):
    schema_version: Literal[1] = 1
    path: str = Field(min_length=1, max_length=4_096)
    language: str | None = Field(default=None, max_length=64)
    content_hash: str = Field(min_length=32, max_length=128)
    name: str | None = Field(default=None, max_length=512)
    kind: str | None = Field(default=None, max_length=128)
    location: SourceLocationV1 | None = None
    confidence: Literal["confirmed", "inferred", "unresolved"] = "confirmed"
    freshness: Literal["current", "stale", "unknown"] = "unknown"

    @field_validator("content_hash")
    @classmethod
    def sha256_hash(cls, value: str) -> str:
        value = value.lower()
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("content_hash must be a SHA-256 hexadecimal digest.")
        return value


# Singular spelling was used by the first local implementation. Keep it as a
# source-compatible alias while exposing the documented CodeFactsV1 contract.
CodeFactV1 = CodeFactsV1


class EvidenceV1(BaseModel):
    schema_version: Literal[1] = 1
    claim: str = Field(min_length=1, max_length=2_000)
    sources: list[SourceLocationV1] = Field(default_factory=list, max_length=64)
    command: str | None = Field(default=None, max_length=4_000)
    passed: bool | None = None
    producer: str = Field(default="unknown", min_length=1, max_length=128)
    recorded_at: str = Field(default_factory=utc_now)
    uncertainty: str = Field(default="", max_length=2_000)

    @model_validator(mode="after")
    def artifact_sized(self) -> "EvidenceV1":
        if len(self.model_dump_json(exclude_none=True)) > MAX_SERIALIZED_CONTRACT_CHARS:
            raise ValueError("Evidence contract is too large to persist as bounded workflow evidence.")
        return self


class GraphNodeV1(BaseModel):
    path: str = Field(min_length=1, max_length=4_096)
    language: str | None = Field(default=None, max_length=64)
    symbol_count: int = Field(ge=0)


class GraphEdgeV1(BaseModel):
    source: str = Field(min_length=1, max_length=4_096)
    target: str = Field(min_length=1, max_length=4_096)
    # Current graph edges are static import-resolution inferences, not a
    # whole-program type-checker proof. Callers should treat them accordingly.
    confidence: Literal["confirmed", "inferred"] = "inferred"


class GraphExportV1(BaseModel):
    """A bounded structural graph.  It intentionally contains no source text."""

    schema_version: Literal[1] = 1
    generated_at: str = Field(default_factory=utc_now)
    root: str
    nodes: list[GraphNodeV1] = Field(default_factory=list)
    edges: list[GraphEdgeV1] = Field(default_factory=list)
    truncated: bool = False
    max_nodes: int = Field(default=200, ge=1, le=10_000)
