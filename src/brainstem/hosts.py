"""Safe local-MCP configuration and capability reporting for coding hosts."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Literal

from ._atomic import atomic_write_text

HOSTS = ("generic", "codex", "claude-code", "cursor", "vscode", "gemini")
HostScope = Literal["project", "user"]
HOST_EXECUTABLES: dict[str, str | None] = {
    "generic": None,
    "codex": "codex",
    "claude-code": "claude",
    "cursor": "cursor-agent",
    "vscode": "code",
    "gemini": "gemini",
}

# These are Brainstem-adapter capabilities, not claims about a host's own
# product. New native host plugins can raise a capability only after their
# contract test proves it.
HOST_CAPABILITIES: dict[str, dict[str, bool]] = {
    host: {
        "mcp": True,
        "session_start": False,
        "workflow_status": True,
        "approval_hooks": False,
        "graph_view": True,
        "project_config": host != "codex",
        "user_config": True,
    }
    for host in HOSTS
}


def _validate_host(host: str) -> str:
    if host not in HOSTS:
        raise ValueError(f"Unknown host '{host}'. Choose: {', '.join(HOSTS)}.")
    return host


def _validate_profile(profile: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", profile):
        raise ValueError("profile must be 1-64 letters, digits, hyphens, or underscores.")
    return profile


def _validate_command(command: str) -> str:
    if not command or len(command) > 4_096 or any(character in command for character in "\r\n\0"):
        raise ValueError("command must be a non-empty executable path/name without control characters.")
    return command


def server_definition(repo_root: Path, profile: str = "readonly", command: str = "brainstem") -> dict:
    """Return the transport-neutral, local-stdio MCP server contract."""
    return {
        "command": _validate_command(command),
        "args": ["serve", "--path", str(repo_root.resolve()), "--profile", _validate_profile(profile)],
    }


def _entry_error(entry: object, repo_root: Path, command: str) -> str | None:
    """Validate an installed Brainstem entry without executing it."""
    if not isinstance(entry, dict):
        return "Brainstem entry must be an object/table."
    if set(entry) != {"command", "args"}:
        return "Brainstem entry must contain only command and args."
    actual_command = entry.get("command")
    args = entry.get("args")
    if actual_command != command:
        return "Brainstem entry command does not match the selected launcher command."
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        return "Brainstem entry args must be a string list."
    expected_prefix = ["serve", "--path", str(repo_root.resolve()), "--profile"]
    if len(args) != 5 or args[:4] != expected_prefix:
        return "Brainstem entry must use the bounded local `serve --path ... --profile ...` argument shape."
    try:
        _validate_profile(args[4])
    except ValueError:
        return "Brainstem entry profile is invalid."
    return None


def host_capabilities(host: str) -> dict[str, bool]:
    return dict(HOST_CAPABILITIES[_validate_host(host)])


def host_cli_status(host: str, *, probe_version: bool = False) -> dict[str, object]:
    """Report an optional host CLI without running configured user commands.

    The executable name is a reviewed, fixed adapter property.  ``--version``
    is executed only by ``host doctor`` and is short-lived; ordinary status
    remains read-only.
    """
    host = _validate_host(host)
    executable = HOST_EXECUTABLES[host]
    if executable is None:
        return {"applicable": False, "available": None, "executable": None, "version": None}
    resolved = shutil.which(executable)
    if resolved is None:
        return {"applicable": True, "available": False, "executable": executable, "version": None}
    report: dict[str, object] = {
        "applicable": True,
        "available": True,
        "executable": executable,
        "path": resolved,
        "version": None,
    }
    if not probe_version:
        return report
    try:
        result = subprocess.run(
            [resolved, "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        report["version_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return report
    if result.returncode == 0:
        report["version"] = (result.stdout or result.stderr).strip()[:500] or "reported no version text"
    else:
        report["version_error"] = (result.stderr or result.stdout).strip()[:500] or f"exit {result.returncode}"
    return report


def _config_root_key(host: str, scope: HostScope) -> str:
    # VS Code's workspace schema uses `servers`. Its documented portable
    # user/Agent-Host location is ~/.copilot/mcp-config.json and uses the
    # cross-host `mcpServers` schema.
    return "servers" if host == "vscode" and scope == "project" else "mcpServers"


def _json_config(host: str, definition: dict, scope: HostScope = "project") -> dict:
    if _config_root_key(host, scope) == "servers":
        return {"servers": {"brainstem": definition}}
    return {"mcpServers": {"brainstem": definition}}


def render_host_config(host: str, repo_root: Path, profile: str = "readonly", command: str = "brainstem") -> str:
    """Return a copy/paste configuration for one known local MCP host."""
    _validate_host(host)
    definition = server_definition(repo_root, profile, command)
    args = definition["args"]
    if host == "codex":
        return "\n".join(
            [
                "# Append to ~/.codex/config.toml (Codex's documented user configuration)",
                "[mcp_servers.brainstem]",
                f"command = {json.dumps(command)}",
                f"args = {json.dumps(args)}",
            ]
        )
    if host == "claude-code":
        return (
            "# Run from this repository. The JSON form preserves Brainstem's "
            "--path/--profile arguments on Windows and Unix shells.\n"
            f"claude mcp add-json --scope project brainstem '{json.dumps(definition)}'"
        )
    config = _json_config(host, definition)
    if host == "generic":
        return (
            "# Generic local-stdio MCP definition. Paste this JSON into any MCP-capable host, "
            "or give it to that host's setup assistant.\n"
            f"{json.dumps(config, indent=2)}"
        )
    headings = {
        "vscode": "# Save as .vscode/mcp.json",
        "cursor": "# Save as .cursor/mcp.json",
        "gemini": "# Save as .gemini/settings.json",
    }
    return f"{headings[host]}\n{json.dumps(config, indent=2)}"


def host_config_path(host: str, repo_root: Path, scope: HostScope = "project") -> Path:
    """Return the exact file Brainstem will change after explicit apply."""
    _validate_host(host)
    if scope not in {"project", "user"}:
        raise ValueError("scope must be project or user.")
    if host == "codex" and scope != "user":
        # Codex CLI documents ~/.codex/config.toml as its active MCP config.
        # Do not create an unproven project-local .codex/config.toml and claim
        # it will be loaded; users can instead use a portable project host.
        raise ValueError("Codex MCP configuration is user-scoped; rerun with --scope user.")
    root = _scope_root(repo_root, scope)
    if host == "generic":
        return (root / ".brain" / "hosts" / "generic-mcp.json") if scope == "project" else root / ".brainstem" / "generic-mcp.json"
    if host == "codex":
        return root / ".codex" / "config.toml"
    if host == "claude-code":
        return root / ".mcp.json" if scope == "project" else root / ".claude.json"
    if host == "cursor":
        return root / ".cursor" / "mcp.json"
    if host == "vscode":
        return root / ".vscode" / "mcp.json" if scope == "project" else root / ".copilot" / "mcp-config.json"
    return root / ".gemini" / "settings.json"


def _scope_root(repo_root: Path, scope: HostScope) -> Path:
    return repo_root.resolve() if scope == "project" else Path.home().resolve()


def _assert_safe_config_target(path: Path, repo_root: Path, scope: HostScope) -> None:
    """Reject configuration paths that traverse a symlink outside their scope."""
    root = _scope_root(repo_root, scope)
    if path.is_symlink():
        raise ValueError(f"Refusing to modify symlinked host config: {path}")
    try:
        path.parent.resolve().relative_to(root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Refusing host config path outside the selected {scope} scope: {path}") from exc


def _read_json_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        detail = exc.msg if isinstance(exc, json.JSONDecodeError) else str(exc)
        raise ValueError(f"Refusing to overwrite invalid JSON config: {path}: {detail}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Refusing to overwrite non-object JSON config: {path}")
    return value


def _read_toml_config(path: Path) -> dict:
    """Read a Codex configuration without ever repairing malformed input.

    TOML is deliberately parsed before Brainstem appends or removes its
    table.  A regex-only update could otherwise turn a damaged user config
    into a silently different configuration.
    """
    if not path.exists():
        return {}
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Refusing to overwrite invalid TOML config: {path}: {exc}") from exc
    if not isinstance(value, dict):  # Defensive: tomllib currently returns a dict.
        raise ValueError(f"Refusing to overwrite non-object TOML config: {path}")
    mcp_servers = value.get("mcp_servers")
    if mcp_servers is not None and not isinstance(mcp_servers, dict):
        raise ValueError(f"Refusing to overwrite non-table 'mcp_servers' in {path}")
    return value


def _codex_block(definition: dict) -> str:
    return "\n".join(
        [
            "[mcp_servers.brainstem]",
            f"command = {json.dumps(definition['command'])}",
            f"args = {json.dumps(definition['args'])}",
        ]
    )


def install_host_config(
    host: str,
    repo_root: Path,
    *,
    scope: HostScope = "project",
    profile: str = "readonly",
    command: str = "brainstem",
    replace: bool = False,
) -> Path:
    """Apply exactly one reviewed MCP configuration change.

    The CLI exposes this only behind ``--apply``. Existing named Brainstem
    entries are never silently overwritten.
    """
    _validate_host(host)
    path = host_config_path(host, repo_root, scope)
    _assert_safe_config_target(path, repo_root, scope)
    definition = server_definition(repo_root, profile, command)
    if host == "codex":
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        _read_toml_config(path)
        block = _codex_block(definition)
        pattern = re.compile(r"(?ms)^\[mcp_servers\.brainstem\]\n.*?(?=^\[|\Z)")
        if pattern.search(text):
            if not replace:
                raise FileExistsError(f"Brainstem is already configured in {path}; rerun with --replace to update only that entry.")
            text = pattern.sub(block + "\n", text).rstrip() + "\n"
        else:
            text = (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"
        # Validate the exact bytes that will be written before changing a
        # user-scoped configuration file.
        try:
            parsed = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:  # pragma: no cover - protected by parser above
            raise ValueError(f"Refusing to write invalid TOML config: {path}: {exc}") from exc
        if not isinstance(parsed.get("mcp_servers"), dict):
            raise ValueError(f"Refusing to write invalid 'mcp_servers' table in {path}")
        return atomic_write_text(path, text)

    config = _read_json_config(path)
    root_key = _config_root_key(host, scope)
    existing = config.get(root_key)
    if existing is None:
        existing = {}
        config[root_key] = existing
    if not isinstance(existing, dict):
        raise ValueError(f"Refusing to overwrite non-object '{root_key}' in {path}")
    if "brainstem" in existing and not replace:
        raise FileExistsError(f"Brainstem is already configured in {path}; rerun with --replace to update only that entry.")
    existing["brainstem"] = definition
    return atomic_write_text(path, json.dumps(config, indent=2, sort_keys=True) + "\n")


def remove_host_config(host: str, repo_root: Path, *, scope: HostScope = "project") -> Path | None:
    """Remove only Brainstem's named configuration entry, never a whole file."""
    _validate_host(host)
    path = host_config_path(host, repo_root, scope)
    _assert_safe_config_target(path, repo_root, scope)
    if not path.exists():
        return None
    if host == "codex":
        text = path.read_text(encoding="utf-8")
        _read_toml_config(path)
        pattern = re.compile(r"(?ms)^\[mcp_servers\.brainstem\]\n.*?(?=^\[|\Z)")
        updated, count = pattern.subn("", text)
        if not count:
            return None
        updated = updated.strip() + "\n"
        try:
            tomllib.loads(updated)
        except tomllib.TOMLDecodeError as exc:  # pragma: no cover - protected by parser above
            raise ValueError(f"Refusing to write invalid TOML config: {path}: {exc}") from exc
        return atomic_write_text(path, updated)
    config = _read_json_config(path)
    root_key = _config_root_key(host, scope)
    entries = config.get(root_key)
    if not isinstance(entries, dict) or "brainstem" not in entries:
        return None
    del entries["brainstem"]
    return atomic_write_text(path, json.dumps(config, indent=2, sort_keys=True) + "\n")


def host_status(host: str, repo_root: Path, *, scope: HostScope = "project", command: str = "brainstem") -> dict[str, object]:
    _validate_host(host)
    path = host_config_path(host, repo_root, scope)
    configured = False
    config_error: str | None = None
    entry_error: str | None = None
    try:
        _assert_safe_config_target(path, repo_root, scope)
        if path.exists():
            if host == "codex":
                config = _read_toml_config(path)
                entries = config.get("mcp_servers", {})
                entry = entries.get("brainstem") if isinstance(entries, dict) else None
            else:
                config = _read_json_config(path)
                entries = config.get(_config_root_key(host, scope), {})
                entry = entries.get("brainstem") if isinstance(entries, dict) else None
            if entry is not None:
                entry_error = _entry_error(entry, repo_root, _validate_command(command))
                configured = entry_error is None
    except ValueError as exc:
        config_error = str(exc)
    return {
        "host": host,
        "scope": scope,
        "config_path": str(path),
        "configured": configured,
        "config_error": config_error,
        "entry_error": entry_error,
        "command_available": shutil.which(command) is not None,
        "host_cli": host_cli_status(host),
        "capabilities": host_capabilities(host),
    }


def render_connect_prompt(repo_root: Path, profile: str = "readonly", command: str = "brainstem") -> str:
    """Give users a safe, product-agnostic instruction for an AI host."""
    definition = server_definition(repo_root, profile, command)
    return "\n".join(
        [
            "Configure this project to use the following local stdio MCP server named `brainstem`.",
            "Do not expose it over HTTP, do not replace existing MCP servers, and do not grant broader permissions.",
            "Keep its command and arguments exactly as shown, then verify the connection by calling `describe_project`.",
            "For every code change, debugging task, implementation plan, or review, call `prepare_task` first with the user's exact task.",
            "Use its bounded evidence packet before opening more files; expand context only for a named missing dependency, symbol, or test.",
            "If the packet says its graph metadata is stale, ask the developer to run `brainstem index` before relying on impact analysis.",
            "If your host requires a config file, translate this standard mcpServers entry into that host's documented schema:",
            json.dumps({"mcpServers": {"brainstem": definition}}, indent=2),
        ]
    )
