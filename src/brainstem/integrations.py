"""Data-only catalog for third-party MCP connections.

Brainstem is an MCP server, not a transparent proxy for arbitrary remote tools.
This module lets a repository declare reviewed peer MCP connections without
storing credentials or executing third-party commands.  A host can consume the
rendered client entry alongside its Brainstem entry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._atomic import atomic_write_text
from .manifest import brain_state_path


CATALOG_FILENAME = "integrations/mcp.json"
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_ENV_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


class MCPConnection(BaseModel):
    """A reviewed, credential-free declaration of one external MCP server."""

    model_config = ConfigDict(extra="forbid")

    name: str
    transport: Literal["stdio", "streamable-http"]
    command: str | None = None
    args: list[str] = Field(default_factory=list, max_length=64)
    url: str | None = None
    # Maps the child-process variable name (or HTTP header name) to the name
    # of an already-existing environment variable. Values are never secrets.
    env_from: dict[str, str] = Field(default_factory=dict, max_length=32)
    description: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not _NAME_RE.fullmatch(value):
            raise ValueError("name must be 1-64 letters, digits, hyphens, or underscores.")
        return value

    @field_validator("command")
    @classmethod
    def valid_command(cls, value: str | None) -> str | None:
        if value is not None and (not value or len(value) > 4_096 or any(char in value for char in "\r\n\0")):
            raise ValueError("command must be a non-empty executable path/name without control characters.")
        return value

    @field_validator("args")
    @classmethod
    def valid_args(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 4_096 or any(char in item for char in "\r\n\0") for item in value):
            raise ValueError("args must be non-empty strings without control characters, at most 4096 characters each.")
        return value

    @field_validator("env_from")
    @classmethod
    def valid_environment_references(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not key or len(key) > 128 or not _ENV_RE.fullmatch(source) for key, source in value.items()):
            raise ValueError("env_from values must be environment-variable names; literal credentials are not allowed.")
        return value

    @model_validator(mode="after")
    def valid_transport_shape(self) -> "MCPConnection":
        if self.transport == "stdio":
            if self.command is None or self.url is not None:
                raise ValueError("stdio connections require command and must not set url.")
        else:
            if self.url is None or self.command is not None or self.args:
                raise ValueError("streamable-http connections require url and must not set command or args.")
            parsed = urlparse(self.url)
            local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            if not (parsed.scheme == "https" or local_http) or not parsed.netloc:
                raise ValueError("streamable-http url must use https (or http only for loopback localhost).")
        return self


def catalog_path(repo_root: Path) -> Path:
    return brain_state_path(repo_root, *Path(CATALOG_FILENAME).parts)


def inspect_connection(source: Path) -> MCPConnection:
    """Parse an external descriptor as data only; it never opens a connection."""
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read MCP connection descriptor: {source}") from exc
    if not isinstance(payload, dict):
        raise ValueError("MCP connection descriptor must be one JSON object.")
    return MCPConnection.model_validate(payload)


def list_connections(repo_root: Path) -> list[MCPConnection]:
    path = catalog_path(repo_root)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("connections", []) if isinstance(payload, dict) else []
        return [MCPConnection.model_validate(entry) for entry in entries]
    except (OSError, json.JSONDecodeError, ValueError):
        # A corrupt catalog must not become executable configuration. Callers
        # get a safe empty list; a later add will surface the condition first.
        return []


def register_connection(repo_root: Path, connection: MCPConnection, *, replace: bool = False) -> Path:
    """Persist one declaration, refusing accidental replacement by default."""
    path = catalog_path(repo_root)
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("connections", []), list):
                raise ValueError("MCP connection catalog has invalid shape; repair it before registering a connection.")
            existing = [MCPConnection.model_validate(item) for item in raw["connections"]]
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("MCP connection catalog cannot be read safely; repair it before registering a connection.") from exc
    else:
        existing = []
    names = {item.name for item in existing}
    if connection.name in names and not replace:
        raise FileExistsError(f"MCP connection '{connection.name}' already exists; pass --replace after reviewing it.")
    merged = [item for item in existing if item.name != connection.name] + [connection]
    rendered = {
        "schema_version": 1,
        "connections": [item.model_dump(mode="json") for item in sorted(merged, key=lambda item: item.name)],
    }
    return atomic_write_text(path, json.dumps(rendered, indent=2, sort_keys=True) + "\n")


def render_connection(repo_root: Path, name: str) -> dict:
    """Render portable client config; environment values remain references."""
    connection = next((item for item in list_connections(repo_root) if item.name == name), None)
    if connection is None:
        raise FileNotFoundError(f"No registered MCP connection named '{name}'.")
    if connection.transport == "stdio":
        entry: dict[str, object] = {"command": connection.command, "args": connection.args}
        if connection.env_from:
            entry["env"] = {key: f"${{{source}}}" for key, source in connection.env_from.items()}
    else:
        entry = {"url": connection.url}
        if connection.env_from:
            entry["headers"] = {key: f"${{{source}}}" for key, source in connection.env_from.items()}
    return {"mcpServers": {connection.name: entry}}
