"""Non-destructive local diagnostics for the Brainstem runtime."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from fastmcp import Client


REQUIRED_MCP_TOOLS = frozenset({"describe_project", "get_context_bundle", "prepare_task", "repository_graph"})


def _mcp_doctor_timeout_s() -> float:
    """Use a bounded timeout even if an environment variable is malformed."""
    try:
        value = float(os.environ.get("BRAINSTEM_MCP_DOCTOR_TIMEOUT_S", "10"))
    except ValueError:
        return 10.0
    return min(max(value, 1.0), 30.0)


def run_mcp_handshake(repo_root: Path) -> dict[str, Any]:
    """Start this installed Brainstem MCP server and verify the stdio protocol.

    This intentionally does not execute a user-configured host command or
    alter its configuration.  It verifies the exact portable stdio server
    that every host adapter points at, using the current Python interpreter
    and a finite timeout.
    """
    root = repo_root.resolve()
    config = {
        "mcpServers": {
            "brainstem-doctor": {
                "command": sys.executable,
                "args": ["-m", "brainstem.mcp_server"],
                "cwd": str(root),
            }
        }
    }

    async def _check() -> list[str]:
        async with Client(config, timeout=_mcp_doctor_timeout_s()) as client:
            return sorted(tool.name for tool in await client.list_tools())

    try:
        tools = asyncio.run(_check())
    except Exception as exc:  # The CLI must report a failed doctor, not crash.
        return {
            "passed": False,
            "timeout_s": _mcp_doctor_timeout_s(),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
    missing = sorted(REQUIRED_MCP_TOOLS.difference(tools))
    return {
        "passed": not missing,
        "timeout_s": _mcp_doctor_timeout_s(),
        "tool_count": len(tools),
        "required_tools": sorted(REQUIRED_MCP_TOOLS),
        "missing_tools": missing,
    }
