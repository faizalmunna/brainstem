from pathlib import Path

import pytest

from brainstem.adapters.base import ModelBackend
from brainstem.agents.runtime import list_runs, load_run, run_agent_turn
from brainstem.agents.team import bootstrap_delivery_team
from brainstem.broker.broker import RequestBroker
from brainstem.broker.budget import CompletionBudget
from brainstem.broker.cache import RequestCache
from brainstem.broker.router import Router
from brainstem.indexer.graph import build_graph
from brainstem.manifest import default_manifest, save_manifest
from brainstem.workflow import start_workflow
from brainstem.workspace import Workspace


class FakeBackend(ModelBackend):
    name = "fake/agent"

    def __init__(self) -> None:
        self.system = ""
        self.prompt = ""

    def is_available(self) -> bool:
        return True

    def complete(self, prompt: str, *, system: str | None = None, **kwargs) -> str:
        self.system = system or ""
        self.prompt = prompt
        return "independent agent report: TOKEN=must-not-be-persisted"


def _workspace_with_delivery_workflow(tmp_path: Path) -> tuple[Workspace, RequestBroker, FakeBackend]:
    (tmp_path / "service.py").write_text("def authenticate(token: str) -> bool:\n    return bool(token)\n", encoding="utf-8")
    save_manifest(tmp_path, default_manifest("agent-runtime"))
    bootstrap_delivery_team(tmp_path)
    start_workflow(tmp_path, "Review authentication behavior", workflow_id="agent-turn", team="delivery")
    workspace = Workspace.open(tmp_path)
    workspace._graph = build_graph(tmp_path, workspace.manifest)
    backend = FakeBackend()
    broker = RequestBroker(RequestCache(tmp_path / ".brain" / "cache" / "test.db"), Router([backend]))
    return workspace, broker, backend


def test_agent_turn_invokes_current_role_with_bounded_packet_and_auditable_metadata(tmp_path):
    workspace, broker, backend = _workspace_with_delivery_workflow(tmp_path)

    result = run_agent_turn(
        workspace,
        broker,
        workflow_id="agent-turn",
        profile_name="explorer",
        budget=CompletionBudget(max_input_tokens=16_000, max_output_tokens=200),
    )

    assert result.run.state == "completed"
    assert result.run.profile == "explorer"
    assert result.run.role == "explorer"
    assert result.run.backend == "fake/agent"
    assert "independent explorer agent" in backend.system
    assert "Bounded repository evidence" in backend.prompt
    assert result.report.startswith("independent agent report")
    persisted = load_run(workspace.repo_root, result.run.id)
    assert persisted.output_sha256 == result.run.output_sha256
    assert persisted.output_chars == len(result.report)
    assert "must-not-be-persisted" not in (workspace.repo_root / ".brain" / "agents" / "runs" / f"{result.run.id}.json").read_text(
        encoding="utf-8"
    )
    assert b"must-not-be-persisted" not in (workspace.repo_root / ".brain" / "cache" / "test.db").read_bytes()
    assert [run.id for run in list_runs(workspace.repo_root, workflow_id="agent-turn")] == [result.run.id]


def test_agent_turn_refuses_a_profile_not_assigned_to_the_current_workflow_role(tmp_path):
    workspace, broker, _backend = _workspace_with_delivery_workflow(tmp_path)

    with pytest.raises(PermissionError, match="assigned to role 'explorer'"):
        run_agent_turn(
            workspace,
            broker,
            workflow_id="agent-turn",
            profile_name="implementer",
            budget=CompletionBudget(max_output_tokens=200),
        )


def test_agent_turn_requires_a_team_bound_workflow_and_index(tmp_path):
    save_manifest(tmp_path, default_manifest("agent-runtime"))
    workspace = Workspace.open(tmp_path)
    start_workflow(tmp_path, "Review auth", workflow_id="unbound")
    backend = FakeBackend()
    broker = RequestBroker(RequestCache(tmp_path / ".brain" / "cache" / "test.db"), Router([backend]))

    with pytest.raises(ValueError, match="team-bound"):
        run_agent_turn(
            workspace,
            broker,
            workflow_id="unbound",
            profile_name="readonly",
            budget=CompletionBudget(max_output_tokens=200),
        )
