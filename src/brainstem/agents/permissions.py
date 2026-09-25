"""Capability permissions enforced at the MCP dispatch boundary.

Every exposed tool is guarded with ``require_permission``. A profile lacking
the required capability receives an error rather than a silently executed
action.
"""

from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    NETWORK = "NETWORK"
    INSTALL = "INSTALL"
    DATABASE = "DATABASE"
    DEPLOY = "DEPLOY"
    DELETE = "DELETE"
    SECRET = "SECRET"


class PermissionDenied(PermissionError):
    def __init__(self, tool: str, required: Permission, profile_name: str) -> None:
        self.tool = tool
        self.required = required
        self.profile_name = profile_name
        super().__init__(
            f"Agent profile '{profile_name}' is not granted {required.value}, "
            f"required by tool '{tool}'."
        )


# Every tool in mcp_server.py must appear here. Deliberately a flat,
# reviewable table rather than annotations scattered across tool
# functions -- auditing what a profile can reach means reading one table.
TOOL_PERMISSIONS: dict[str, Permission] = {
    "describe_project": Permission.READ,
    "get_rules": Permission.READ,
    "query_context": Permission.READ,
    "get_context_bundle": Permission.READ,
    "prepare_task": Permission.READ,
    "find_related": Permission.READ,
    "check_history": Permission.READ,
    "list_skills": Permission.READ,
    "list_skill_packs": Permission.READ,
    "list_agents": Permission.READ,
    "record_decision": Permission.WRITE,
    "propose_capability": Permission.WRITE,
    "run_verification": Permission.EXECUTE,
    "record_skill_usage": Permission.WRITE,
    "get_skill_usage_stats": Permission.READ,
    "list_teams": Permission.READ,
    "get_team": Permission.READ,
    "propose_agent_profile": Permission.READ,
    "start_workflow": Permission.WRITE,
    "get_workflow_state": Permission.READ,
    "get_next_work_item": Permission.READ,
    "record_workflow_artifact": Permission.WRITE,
    "record_workflow_verification": Permission.WRITE,
    "run_workflow_verification": Permission.EXECUTE,
    "request_workflow_transition": Permission.WRITE,
}


def require_permission(tool_name: str, profile) -> None:
    """Raise PermissionDenied if `profile` doesn't grant the permission
    `tool_name` requires. Call this as the first line of every tool
    function -- see mcp_server.py."""
    required = TOOL_PERMISSIONS.get(tool_name)
    if required is None:
        raise KeyError(f"Tool '{tool_name}' has no entry in TOOL_PERMISSIONS -- add one.")
    if required not in profile.permissions:
        raise PermissionDenied(tool_name, required, profile.name)
