"""Durable, evidence-gated engineering workflows.

Brainstem coordinates a workflow but never pretends to be an agent runner:
hosts and humans do the work, while this module stores the task, artifacts,
verification evidence, and state transitions in the repository's ``.brain``
directory.  That makes completion auditable across sessions and host tools.
"""

from __future__ import annotations

import re
import uuid
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .manifest import brain_dir
from .audit import record_audit

WORKFLOWS_DIRNAME = "workflows"
WORKFLOW_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_TASK_CHARS = 4_000
MAX_ARTIFACT_CHARS = 16_000
MAX_NOTE_CHARS = 2_000


class WorkflowArtifact(BaseModel):
    kind: str
    value: str
    status: str = "recorded"
    recorded_at: str
    recorded_by: str = "unknown"
    evidence: str = "manual"  # manual | executed; only executed verification can pass a gate


class WorkflowEvent(BaseModel):
    from_state: str | None = None
    to_state: str
    at: str
    by: str = "unknown"
    note: str = ""


class Workflow(BaseModel):
    id: str
    task: str
    mode: str
    state: str = "intake"
    created_at: str
    updated_at: str
    artifacts: list[WorkflowArtifact] = Field(default_factory=list)
    history: list[WorkflowEvent] = Field(default_factory=list)


MODES = {"fast", "standard", "high-risk"}
STATES = {
    "intake",
    "context_ready",
    "design_review",
    "planned",
    "implementing",
    "verification",
    "review",
    "complete",
    "blocked",
    "cancelled",
}
NEXT_STATES: dict[str, set[str]] = {
    "intake": {"context_ready", "blocked", "cancelled"},
    "context_ready": {"design_review", "planned", "blocked", "cancelled"},
    "design_review": {"planned", "blocked", "cancelled"},
    "planned": {"implementing", "blocked", "cancelled"},
    "implementing": {"verification", "blocked", "cancelled"},
    "verification": {"review", "implementing", "blocked", "cancelled"},
    "review": {"complete", "implementing", "blocked", "cancelled"},
    "blocked": STATES - {"blocked", "complete"},
    "complete": set(),
    "cancelled": set(),
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def workflows_dir(repo_root: Path) -> Path:
    return brain_dir(repo_root) / WORKFLOWS_DIRNAME


def _validate_id(workflow_id: str) -> str:
    if not WORKFLOW_ID_RE.fullmatch(workflow_id):
        raise ValueError("Workflow id must be 1-64 letters, numbers, dots, underscores, or hyphens.")
    return workflow_id


def workflow_path(repo_root: Path, workflow_id: str) -> Path:
    return workflows_dir(repo_root) / f"{_validate_id(workflow_id)}.json"


def _save(repo_root: Path, workflow: Workflow) -> Path:
    path = workflow_path(repo_root, workflow.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(workflow.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    return path


def start_workflow(repo_root: Path, task: str, mode: str = "standard", workflow_id: str = "") -> Workflow:
    """Create a workflow without performing any external action."""
    task = task.strip()
    if not task:
        raise ValueError("Workflow task cannot be empty.")
    if len(task) > MAX_TASK_CHARS:
        raise ValueError(f"Workflow task cannot exceed {MAX_TASK_CHARS} characters.")
    if mode not in MODES:
        raise ValueError(f"Unknown workflow mode '{mode}'. Choose: {', '.join(sorted(MODES))}.")
    workflow_id = _validate_id(workflow_id) if workflow_id else f"wf-{uuid.uuid4().hex[:12]}"
    path = workflow_path(repo_root, workflow_id)
    if path.exists():
        raise FileExistsError(f"Workflow '{workflow_id}' already exists.")
    now = _now()
    workflow = Workflow(
        id=workflow_id,
        task=task,
        mode=mode,
        created_at=now,
        updated_at=now,
        history=[WorkflowEvent(to_state="intake", at=now, by="system", note="Workflow created")],
    )
    _save(repo_root, workflow)
    record_audit(
        repo_root, action="workflow.start", actor="system", outcome="created", workflow_id=workflow.id, detail=task
    )
    return workflow


def load_workflow(repo_root: Path, workflow_id: str) -> Workflow:
    path = workflow_path(repo_root, workflow_id)
    if not path.exists():
        raise FileNotFoundError(f"No workflow named '{workflow_id}' at {path}.")
    return Workflow.model_validate_json(path.read_text(encoding="utf-8"))


def list_workflows(repo_root: Path) -> list[Workflow]:
    directory = workflows_dir(repo_root)
    if not directory.is_dir():
        return []
    return sorted(
        (Workflow.model_validate_json(path.read_text(encoding="utf-8")) for path in directory.glob("*.json")),
        key=lambda workflow: workflow.created_at,
        reverse=True,
    )


def record_artifact(
    repo_root: Path,
    workflow_id: str,
    kind: str,
    value: str,
    *,
    status: str = "recorded",
    by: str = "unknown",
    evidence: str = "manual",
) -> Workflow:
    workflow = load_workflow(repo_root, workflow_id)
    kind, value, status, evidence = kind.strip(), value.strip(), status.strip(), evidence.strip()
    if not kind or not value or not status:
        raise ValueError("Artifact kind, value, and status cannot be empty.")
    if len(kind) > 64 or len(status) > 64:
        raise ValueError("Artifact kind and status cannot exceed 64 characters.")
    if len(value) > MAX_ARTIFACT_CHARS:
        raise ValueError(f"Artifact value cannot exceed {MAX_ARTIFACT_CHARS} characters.")
    if len(by) > 128:
        raise ValueError("Artifact author cannot exceed 128 characters.")
    if evidence not in {"manual", "executed"}:
        raise ValueError("Artifact evidence must be 'manual' or 'executed'.")
    workflow.artifacts.append(
        WorkflowArtifact(kind=kind, value=value, status=status, recorded_at=_now(), recorded_by=by, evidence=evidence)
    )
    workflow.updated_at = _now()
    _save(repo_root, workflow)
    record_audit(
        repo_root,
        action="workflow.artifact",
        actor=by,
        outcome=status,
        workflow_id=workflow.id,
        detail=f"{kind}:{value}",
    )
    return workflow


def record_verification(
    repo_root: Path,
    workflow_id: str,
    summary: str,
    *,
    passed: bool,
    by: str = "unknown",
    evidence: str = "executed",
) -> Workflow:
    return record_artifact(
        repo_root,
        workflow_id,
        "verification",
        summary,
        status="passed" if passed else "failed",
        by=by,
        evidence=evidence,
    )


def record_execution_verification(repo_root: Path, workflow_id: str, result, *, by: str) -> Workflow:
    """Store a compact, tamper-evident summary of an actual verifier run.

    Full stdout/stderr can contain secrets and can be enormous.  The workflow
    instead records the executed command, exit status, duration, and a SHA-256
    digest of each output stream, sufficient to link an audit record without
    treating agent-provided prose as proof.
    """
    checks = [
        {
            "command": item.command,
            "exit_code": item.exit_code,
            "duration_s": round(item.duration_s, 3),
            "stdout_sha256": hashlib.sha256(item.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(item.stderr.encode()).hexdigest(),
        }
        for item in result.results
    ]
    summary = json.dumps({"checks": checks, "passed": result.passed}, sort_keys=True, separators=(",", ":"))
    return record_verification(repo_root, workflow_id, summary, passed=result.passed, by=by, evidence="executed")


def _has_artifact(workflow: Workflow, kind: str, status: str | None = None) -> bool:
    return any(item.kind == kind and (status is None or item.status == status) for item in workflow.artifacts)


def _last_artifact_index(
    workflow: Workflow, kind: str, status: str | None = None, evidence: str | None = None
) -> int | None:
    """Find evidence by append order, which is the durable event order.

    Wall-clock timestamps can be reordered by differently configured hosts;
    the artifact list is written atomically in its actual receipt order.
    """
    for index in range(len(workflow.artifacts) - 1, -1, -1):
        item = workflow.artifacts[index]
        if item.kind == kind and (status is None or item.status == status) and (evidence is None or item.evidence == evidence):
            return index
    return None


def _require_fresh_verification(workflow: Workflow) -> int:
    verification = _last_artifact_index(workflow, "verification", "passed", "executed")
    implementation = _last_artifact_index(workflow, "implementation")
    if verification is None or (implementation is not None and verification < implementation):
        raise ValueError("Cannot proceed without a passed verification after the latest implementation artifact.")
    return verification


def _require_transition_evidence(workflow: Workflow, target: str) -> None:
    if target == "planned":
        if workflow.mode != "fast" and not _has_artifact(workflow, "design", "approved"):
            raise ValueError("Cannot plan standard/high-risk work without an approved design artifact.")
        if workflow.mode == "high-risk" and not _has_artifact(workflow, "threat_review", "approved"):
            raise ValueError("Cannot plan high-risk work without an approved threat_review artifact.")
    if target == "implementing" and not _has_artifact(workflow, "plan"):
        raise ValueError("Cannot implement without a plan artifact.")
    if target == "implementing" and workflow.mode != "fast" and not _has_artifact(workflow, "test_plan"):
        raise ValueError("Cannot implement standard/high-risk work without a test_plan artifact.")
    if target == "verification" and not _has_artifact(workflow, "implementation"):
        raise ValueError("Cannot verify without an implementation artifact.")
    if target == "review":
        _require_fresh_verification(workflow)
    if target == "complete":
        verification = _require_fresh_verification(workflow)
        review = _last_artifact_index(workflow, "review", "approved")
        if review is None or review < verification:
            raise ValueError("Cannot complete without an approved review after the latest passed verification.")
        implementation = _last_artifact_index(workflow, "implementation")
        if workflow.mode == "high-risk" and implementation is not None:
            if workflow.artifacts[review].recorded_by == workflow.artifacts[implementation].recorded_by:
                raise ValueError("High-risk work requires review approval by an actor other than the implementer.")


def transition_workflow(
    repo_root: Path, workflow_id: str, target: str, *, by: str = "unknown", note: str = ""
) -> Workflow:
    workflow = load_workflow(repo_root, workflow_id)
    target = target.strip()
    if len(note) > MAX_NOTE_CHARS:
        raise ValueError(f"Workflow note cannot exceed {MAX_NOTE_CHARS} characters.")
    if len(by) > 128:
        raise ValueError("Workflow actor cannot exceed 128 characters.")
    if target not in STATES:
        raise ValueError(f"Unknown workflow state '{target}'.")
    if target not in NEXT_STATES[workflow.state]:
        raise ValueError(f"Cannot transition workflow '{workflow_id}' from {workflow.state} to {target}.")
    if workflow.state == "context_ready" and target == "planned" and workflow.mode != "fast":
        raise ValueError("Only fast workflows may skip design_review.")
    _require_transition_evidence(workflow, target)
    now = _now()
    workflow.history.append(WorkflowEvent(from_state=workflow.state, to_state=target, at=now, by=by, note=note))
    workflow.state = target
    workflow.updated_at = now
    _save(repo_root, workflow)
    record_audit(
        repo_root,
        action="workflow.transition",
        actor=by,
        outcome=target,
        workflow_id=workflow.id,
        detail=note,
    )
    return workflow


def next_work_item(workflow: Workflow) -> dict[str, Any]:
    """Return a compact, host-neutral next-action packet.

    This is deliberately data rather than a host-specific prompt. Hosts with
    subagents can hand it to a scoped role; hosts without them can show it to
    one agent or a human. Either way the workflow engine remains the gate.
    """
    actions = {
        "intake": "Retrieve the minimal relevant repository context and record a context artifact.",
        "context_ready": "For standard/high-risk work, record a reviewed design; fast work may transition to planned.",
        "design_review": "Create a small implementation plan with tests and record it as a plan artifact.",
        "planned": "Implement the next bounded change and record changed files or a work report.",
        "implementing": "Run deterministic verification and record its command/output summary and pass/fail result.",
        "verification": "If verification passed, request an independent review; otherwise return to implementation.",
        "review": "Record an approved review, or return to implementation with the findings.",
        "blocked": "Record the blocking condition and transition back to the appropriate active state when resolved.",
        "complete": "Workflow is complete; record any reusable decision or skill outcome.",
        "cancelled": "Workflow is cancelled; no further work should be performed without a new workflow.",
    }
    roles = {
        "intake": "explorer",
        "context_ready": "designer",
        "design_review": "planner",
        "planned": "implementer",
        "implementing": "tester",
        "verification": "reviewer",
        "review": "reviewer",
        "blocked": "coordinator",
        "complete": "coordinator",
        "cancelled": "coordinator",
    }
    required_artifacts = {
        "intake": ["context"],
        "context_ready": ["design"] if workflow.mode != "fast" else ["plan"],
        "design_review": ["plan", "test_plan"] if workflow.mode != "fast" else ["plan"],
        "planned": ["implementation"],
        "implementing": ["executed verification"],
        "verification": ["approved review"],
        "review": ["approved review"],
        "blocked": ["blocking-condition"],
        "complete": [],
        "cancelled": [],
    }
    recommended_tools = {
        "intake": ["get_context_bundle", "record_workflow_artifact"],
        "context_ready": ["record_workflow_artifact", "request_workflow_transition"],
        "design_review": ["record_workflow_artifact", "request_workflow_transition"],
        "planned": ["record_workflow_artifact", "request_workflow_transition"],
        "implementing": ["run_workflow_verification"],
        "verification": ["record_workflow_artifact", "request_workflow_transition"],
        "review": ["record_workflow_artifact", "request_workflow_transition"],
        "blocked": ["record_workflow_artifact", "request_workflow_transition"],
        "complete": ["record_decision", "record_skill_usage"],
        "cancelled": [],
    }
    return {
        "packet_version": 1,
        "workflow_id": workflow.id,
        "state": workflow.state,
        "mode": workflow.mode,
        "role": roles[workflow.state],
        "next_action": actions[workflow.state],
        "required_artifacts": required_artifacts[workflow.state],
        "recommended_tools": recommended_tools[workflow.state],
        "context_budget_chars": 12_000,
        "review_policy": "independent reviewer required for high-risk work",
        "allowed_transitions": sorted(NEXT_STATES[workflow.state]),
    }
