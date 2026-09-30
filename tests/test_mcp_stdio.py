import asyncio
import json
import os
import sys

from fastmcp import Client

from brainstem.agents.profile import AgentProfile
from brainstem.manifest import default_manifest, save_manifest
from brainstem.mcp_server import build_server
from brainstem.workspace import Workspace


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
    assert "repository_graph" in names
    assert "workflow_begin" in names
    assert "record_workflow_evidence" in names
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


def test_goal_workflow_scope_is_enforced_after_the_profile_permission_check(tmp_path):
    """A write-capable host cannot enlarge a read-only approved task scope."""
    save_manifest(tmp_path, default_manifest("workflow-scope"))
    workspace = Workspace.open(tmp_path)
    server = build_server(workspace, AgentProfile(name="writer", permissions={"READ", "WRITE"}))

    async def _exercise_scope():
        async with Client(server) as client:
            started = await client.call_tool(
                "workflow_begin",
                {"goal": {"goal": "Inspect only", "allowed_capabilities": ["READ"]}, "workflow_id": "read-only"},
                raise_on_error=False,
            )
            artifact = await client.call_tool(
                "record_workflow_artifact",
                {"workflow_id": "read-only", "kind": "plan", "value": "must not be written"},
                raise_on_error=False,
            )
            return started, artifact

    started, artifact = asyncio.run(_exercise_scope())
    workspace.close()

    assert started.is_error is False
    assert artifact.is_error is True


def test_mcp_skill_listing_is_bounded_by_default(tmp_path):
    save_manifest(tmp_path, default_manifest("skill-list-bound"))
    workspace = Workspace.open(tmp_path)
    server = build_server(workspace)

    async def _list_skills():
        async with Client(server) as client:
            default_result = await client.call_tool("list_skills", {}, raise_on_error=False)
            invalid_result = await client.call_tool("list_skills", {"limit": 101}, raise_on_error=False)
            return default_result, invalid_result

    default_result, invalid_result = asyncio.run(_list_skills())
    workspace.close()

    assert default_result.is_error is False
    assert isinstance(default_result.data, list)
    assert len(default_result.data) == 50
    assert invalid_result.data == [{"error": "limit must be between 1 and 100"}]
