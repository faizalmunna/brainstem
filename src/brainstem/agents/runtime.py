"""Provider-backed, role-scoped agent turns.

This module is intentionally narrower than a general autonomous shell.  A
turn is a real model invocation for the role currently assigned by a
team-bound workflow.  It receives a bounded task packet and produces a report
for a human or connected host to review.  It cannot execute commands, edit
source, advance workflow state, or expand its own permissions.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .._atomic import atomic_write_text
from ..audit import record_audit
from ..broker.broker import RequestBroker
from ..broker.budget import CompletionBudget
from ..manifest import brain_state_path
from ..retrieval.task_packet import build_task_packet
from ..workflow import load_workflow, next_work_item, require_workflow_actor, require_workflow_capability
from ..workspace import Workspace
from .permissions import Permission
from .profile import AgentProfile, load_profile


RUNS_DIRNAME = "runs"
MAX_AGENT_OUTPUT_CHARS = 64_000

AgentRunState = Literal["running", "completed", "failed"]


ROLE_INSTRUCTIONS: dict[str, str] = {
    "explorer": "Map the relevant code and dependencies. Identify evidence gaps; do not invent implementation details.",
    "designer": "Compare feasible designs, state trade-offs, and recommend a bounded design that respects repository rules.",
    "planner": "Produce a small ordered implementation and test plan with observable acceptance checks.",
    "implementer": "Describe the smallest safe implementation change. Do not claim files were edited or tests passed unless evidence says so.",
    "tester": "Identify the deterministic verification needed and distinguish proposed checks from checks that actually ran.",
    "reviewer": "Independently inspect the supplied evidence for correctness, risk, missing tests, and unmet acceptance criteria.",
    "coordinator": "Identify the single next workflow action and missing evidence; do not bypass a workflow gate.",
}


class AgentRun(BaseModel):
    """Durable metadata proving a role-scoped model turn occurred.

    Prompt/source excerpts and response text are intentionally not stored in
    this record.  They may contain proprietary source or model-provided
    material.  The command returns the report to its caller, while a digest
    makes later audit correlation possible without retaining that content.
    """

    id: str
    workflow_id: str
    profile: str
    role: str
    state: AgentRunState
    created_at: str
    completed_at: str | None = None
    packet_sha256: str
    backend: str | None = None
    cache_hit: bool | None = None
    input_tokens_estimated: int | None = None
    output_tokens_estimated: int | None = None
    output_sha256: str | None = None
    output_chars: int | None = None
    failure_kind: str | None = None


class AgentTurnResult(BaseModel):
    run: AgentRun
    report: str = Field(max_length=MAX_AGENT_OUTPUT_CHARS)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def runs_dir(repo_root: Path) -> Path:
    return brain_state_path(repo_root, "agents", RUNS_DIRNAME)


def run_path(repo_root: Path, run_id: str) -> Path:
    token = run_id.removeprefix("run-")
    if not run_id.startswith("run-") or len(token) != 12 or any(char not in "0123456789abcdef" for char in token):
        raise ValueError("Invalid agent run id.")
    return brain_state_path(repo_root, "agents", RUNS_DIRNAME, f"{run_id}.json")


def save_run(repo_root: Path, run: AgentRun) -> Path:
    path = run_path(repo_root, run.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_text(path, run.model_dump_json(indent=2) + "\n")


def load_run(repo_root: Path, run_id: str) -> AgentRun:
    path = run_path(repo_root, run_id)
    if not path.exists():
        raise FileNotFoundError(f"No agent run named '{run_id}' at {path}.")
    return AgentRun.model_validate_json(path.read_text(encoding="utf-8"))


def list_runs(repo_root: Path, *, workflow_id: str | None = None) -> list[AgentRun]:
    directory = runs_dir(repo_root)
    if not directory.is_dir():
        return []
    runs = [AgentRun.model_validate_json(path.read_text(encoding="utf-8")) for path in directory.glob("run-*.json")]
    if workflow_id is not None:
        runs = [run for run in runs if run.workflow_id == workflow_id]
    return sorted(runs, key=lambda run: run.created_at, reverse=True)


def _packet_digest(packet: dict) -> str:
    return hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _system_prompt(profile: AgentProfile, role: str, next_action: str) -> str:
    permissions = ", ".join(sorted(permission.value for permission in profile.permissions)) or "none"
    role_instruction = ROLE_INSTRUCTIONS.get(role, "Follow the current workflow assignment and report only supported conclusions.")
    return f"""You are Brainstem's independent {role} agent, profile '{profile.name}'.

Your assigned action is: {next_action}
Role focus: {role_instruction}
Your granted Brainstem capabilities are: {permissions}.

You are receiving a bounded, inspectable repository-evidence packet. Treat it
as the only source of code evidence for this turn. Do not claim to have run a
command, changed a file, accessed a credential, called a tool, or completed a
workflow transition. This agent turn cannot perform those actions.

Return a concise report with: conclusion, evidence cited by file/symbol when
available, uncertainty or risks, and the next required workflow evidence. Do
not expose credentials or reproduce large source excerpts."""


def _prompt(workflow_task: str, packet: dict) -> str:
    return (
        "Workflow task:\n"
        + workflow_task
        + "\n\nBounded repository evidence (JSON):\n"
        + json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    )


def run_agent_turn(
    workspace: Workspace,
    broker: RequestBroker,
    *,
    workflow_id: str,
    profile_name: str,
    budget: CompletionBudget,
    prefer_local: bool = False,
) -> AgentTurnResult:
    """Execute one model turn for the workflow's currently assigned agent.

    The CLI is the human-controlled entry point.  This function does not
    expose a model-call MCP tool because a connected agent must not spend
    provider budget or select another model on its own authority.
    """
    workflow = load_workflow(workspace.repo_root, workflow_id)
    if not workflow.team:
        raise ValueError("Agent turns require a team-bound workflow; start the workflow with --team delivery.")
    profile = load_profile(workspace.repo_root, profile_name)
    if Permission.READ not in profile.permissions:
        raise PermissionError(f"Agent profile '{profile.name}' needs READ to receive a bounded task packet.")
    require_workflow_capability(workspace.repo_root, workflow_id, Permission.READ)
    require_workflow_actor(workspace.repo_root, workflow_id, profile.name)
    if workspace.graph is None:
        raise ValueError("No repository index found. Run `brainstem index` before starting an agent turn.")

    item = next_work_item(workflow)
    role = str(item["role"])
    packet = build_task_packet(
        workspace.repo_root,
        workspace.graph,
        workspace.memory,
        workflow.task,
        vector_store=workspace.vector_store,
    )
    run = AgentRun(
        id=f"run-{uuid.uuid4().hex[:12]}",
        workflow_id=workflow.id,
        profile=profile.name,
        role=role,
        state="running",
        created_at=_now(),
        packet_sha256=_packet_digest(packet),
    )
    save_run(workspace.repo_root, run)

    try:
        result = broker.complete(
            _prompt(workflow.task, packet),
            system=_system_prompt(profile, role, str(item["next_action"])),
            prefer_local=prefer_local,
            # Unlike an ad-hoc ask, an agent report can include proprietary
            # source-derived detail. Do not retain it in the response cache;
            # AgentRun persists only its digest and aggregate token metadata.
            use_cache=False,
            budget=budget,
        )
    except Exception as exc:
        failed = run.model_copy(update={"state": "failed", "completed_at": _now(), "failure_kind": type(exc).__name__})
        save_run(workspace.repo_root, failed)
        record_audit(
            workspace.repo_root,
            action="agent.turn",
            actor=f"agent:{profile.name}",
            outcome="failed",
            workflow_id=workflow.id,
            detail=type(exc).__name__,
        )
        raise

    report = result.text[:MAX_AGENT_OUTPUT_CHARS]
    completed = run.model_copy(
        update={
            "state": "completed",
            "completed_at": _now(),
            "backend": result.backend,
            "cache_hit": result.cache_hit,
            "input_tokens_estimated": result.input_tokens_estimated,
            "output_tokens_estimated": result.output_tokens_estimated,
            "output_sha256": hashlib.sha256(report.encode("utf-8")).hexdigest(),
            "output_chars": len(report),
        }
    )
    save_run(workspace.repo_root, completed)
    record_audit(
        workspace.repo_root,
        action="agent.turn",
        actor=f"agent:{profile.name}",
        outcome="completed",
        workflow_id=workflow.id,
        detail=f"role={role}; backend={result.backend}; output_sha256={completed.output_sha256}",
    )
    return AgentTurnResult(run=completed, report=report)
