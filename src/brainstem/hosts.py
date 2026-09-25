"""Explicit configuration snippets for supported local MCP hosts."""

from __future__ import annotations

import json
from pathlib import Path

HOSTS = ("generic", "codex", "claude-code", "cursor", "vscode", "gemini")


def server_definition(repo_root: Path, profile: str = "readonly", command: str = "brainstem") -> dict:
    """Return the transport-neutral local stdio MCP contract.

    This deliberately describes a command and argument vector, not an HTTP
    endpoint. A local stdio server avoids exposing a repository or permission
    profile on the network, and every conforming MCP host can translate this
    object into its own configuration format.
    """
    return {
        "command": command,
        "args": ["serve", "--path", str(repo_root.resolve()), "--profile", profile],
    }


def render_host_config(host: str, repo_root: Path, profile: str = "readonly", command: str = "brainstem") -> str:
    """Return a copy/paste configuration for one known local MCP host."""
    if host not in HOSTS:
        raise ValueError(f"Unknown host '{host}'. Choose: {', '.join(HOSTS)}.")
    definition = server_definition(repo_root, profile, command)
    args = definition["args"]
    if host == "codex":
        return "\n".join(
            [
                "# Append to .codex/config.toml in this repository",
                "[mcp_servers.brainstem]",
                f"command = {json.dumps(command)}",
                f"args = {json.dumps(args)}",
            ]
        )
    if host == "claude-code":
        # Claude Code's Windows CLI can consume child-process flags such as
        # --path even after `--`. Its JSON form keeps the child argv intact.
        config = definition
        return (
            "# Run from this repository. The JSON form preserves Brainstem's "
            "--path/--profile arguments on Windows and Unix shells.\n"
            f"claude mcp add-json --scope project brainstem '{json.dumps(config)}'"
        )
    config = {"mcpServers": {"brainstem": definition}}
    if host == "generic":
        return (
            "# Generic local-stdio MCP definition. Paste this JSON into any MCP-capable host, "
            "or give it to that host's setup assistant.\n"
            f"{json.dumps(config, indent=2)}"
        )
    if host == "vscode":
        config = {"servers": config["mcpServers"]}
        heading = "# Save as .vscode/mcp.json"
    elif host == "cursor":
        heading = "# Save as .cursor/mcp.json"
    else:
        heading = "# Save as .gemini/settings.json"
    return f"{heading}\n{json.dumps(config, indent=2)}"


def render_connect_prompt(repo_root: Path, profile: str = "readonly", command: str = "brainstem") -> str:
    """Give users a safe, product-agnostic instruction for an AI host.

    It is useful where a host can configure MCP from a natural-language
    request but has no dedicated Brainstem installer. The command is JSON so
    path quoting survives Windows and Unix without shell interpolation.
    """
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
