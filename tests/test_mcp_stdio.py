import asyncio
import json
import os
import sys

from fastmcp import Client

from brainstem.manifest import default_manifest, save_manifest


def _mcp_client_timeout_s() -> float:
    """Keep native protocol tests strict while permitting slower CPU emulation."""
    return float(os.environ.get("BRAINSTEM_TEST_MCP_TIMEOUT_S", "10"))


def test_mcp_server_completes_stdio_handshake_and_advertises_read_tools(tmp_path):
    """Exercise the real subprocess protocol, not just server construction."""
    save_manifest(tmp_path, default_manifest("stdio-smoke"))
    config = {
        "mcpServers": {
            "brainstem": {
                "command": sys.executable,
                "args": ["-m", "brainstem.mcp_server"],
                "cwd": str(tmp_path),
            }
        }
    }

    async def _list_tools() -> list[str]:
        async with Client(config, timeout=_mcp_client_timeout_s()) as client:
            return [tool.name for tool in await client.list_tools()]

    names = asyncio.run(_list_tools())

    assert "describe_project" in names
    assert "get_context_bundle" in names
    assert "prepare_task" in names
    assert "run_workflow_verification" in names


def test_mcp_denied_write_is_recorded_without_storing_tool_arguments(tmp_path):
    save_manifest(tmp_path, default_manifest("audit-smoke"))
    config = {
        "mcpServers": {
            "brainstem": {
                "command": sys.executable,
                "args": ["-m", "brainstem.mcp_server"],
                "cwd": str(tmp_path),
            }
        }
    }

    async def _deny_write():
        async with Client(config, timeout=_mcp_client_timeout_s()) as client:
            return await client.call_tool(
                "record_decision",
                {"title": "secret-title", "body": "secret-body"},
                raise_on_error=False,
            )

    result = asyncio.run(_deny_write())

    assert result.is_error is True
    events = (tmp_path / ".brain" / "audit" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    event = json.loads(events[-1])
    assert event["action"] == "mcp.record_decision"
    assert event["outcome"] == "denied"
    assert "secret-title" not in events[-1]
    assert "secret-body" not in events[-1]
