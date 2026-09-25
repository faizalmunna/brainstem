import pytest

from brainstem.workflow import (
    list_workflows,
    load_workflow,
    next_work_item,
    record_artifact,
    record_execution_verification,
    record_verification,
    start_workflow,
    transition_workflow,
)
from brainstem.verify import CommandResult, VerificationResult


def _to_verification(repo_root, workflow_id):
    transition_workflow(repo_root, workflow_id, "context_ready", by="test")
    transition_workflow(repo_root, workflow_id, "design_review", by="test")
    record_artifact(repo_root, workflow_id, "design", "Reviewed design", status="approved", by="reviewer")
    workflow = load_workflow(repo_root, workflow_id)
    if workflow.mode == "high-risk":
        record_artifact(repo_root, workflow_id, "threat_review", "No unmitigated threats", status="approved", by="security")
    transition_workflow(repo_root, workflow_id, "planned", by="test")
    record_artifact(repo_root, workflow_id, "plan", "Task 1 with test", by="planner")
    if workflow.mode != "fast":
        record_artifact(repo_root, workflow_id, "test_plan", "Regression and unit cases", by="tester")
    transition_workflow(repo_root, workflow_id, "implementing", by="test")
    record_artifact(repo_root, workflow_id, "implementation", "src/example.py", by="implementer")
    transition_workflow(repo_root, workflow_id, "verification", by="test")


def test_workflow_is_persisted_and_lists_newest_first(tmp_path):
    first = start_workflow(tmp_path, "Fix authentication", workflow_id="first")
    second = start_workflow(tmp_path, "Add tests", mode="fast", workflow_id="second")

    assert load_workflow(tmp_path, first.id).task == "Fix authentication"
    assert [workflow.id for workflow in list_workflows(tmp_path)] == [second.id, first.id]
    packet = next_work_item(second)
    assert packet["state"] == "intake"
    assert packet["packet_version"] == 1
    assert packet["role"] == "explorer"
    assert packet["required_artifacts"] == ["context"]
    assert "get_context_bundle" in packet["recommended_tools"]


def test_workflow_requires_verification_and_review_before_completion(tmp_path):
    workflow = start_workflow(tmp_path, "Change payment authorization", mode="high-risk", workflow_id="risk")
    _to_verification(tmp_path, workflow.id)

    with pytest.raises(ValueError, match="passed verification"):
        transition_workflow(tmp_path, workflow.id, "review")

    record_verification(tmp_path, workflow.id, "pytest: 12 passed", passed=True, by="tester")
    transition_workflow(tmp_path, workflow.id, "review", by="reviewer")

    with pytest.raises(ValueError, match="approved review"):
        transition_workflow(tmp_path, workflow.id, "complete")

    record_artifact(tmp_path, workflow.id, "review", "No blocking findings", status="approved", by="reviewer")
    complete = transition_workflow(tmp_path, workflow.id, "complete", by="reviewer")
    assert complete.state == "complete"


def test_workflow_rejects_invalid_ids_and_illegal_transitions(tmp_path):
    with pytest.raises(ValueError, match="Workflow id"):
        start_workflow(tmp_path, "x", workflow_id="../escape")

    workflow = start_workflow(tmp_path, "x", workflow_id="valid")
    with pytest.raises(ValueError, match="Cannot transition"):
        transition_workflow(tmp_path, workflow.id, "complete")


def test_standard_workflow_cannot_skip_design_or_plan(tmp_path):
    workflow = start_workflow(tmp_path, "Refactor module", workflow_id="standard")
    transition_workflow(tmp_path, workflow.id, "context_ready")
    with pytest.raises(ValueError, match="Only fast"):
        transition_workflow(tmp_path, workflow.id, "planned")
    transition_workflow(tmp_path, workflow.id, "design_review")
    with pytest.raises(ValueError, match="approved design"):
        transition_workflow(tmp_path, workflow.id, "planned")


def test_standard_workflow_requires_test_plan_before_implementation(tmp_path):
    workflow = start_workflow(tmp_path, "Refactor module", workflow_id="test-plan")
    transition_workflow(tmp_path, workflow.id, "context_ready")
    transition_workflow(tmp_path, workflow.id, "design_review")
    record_artifact(tmp_path, workflow.id, "design", "design", status="approved")
    transition_workflow(tmp_path, workflow.id, "planned")
    record_artifact(tmp_path, workflow.id, "plan", "plan")

    with pytest.raises(ValueError, match="test_plan"):
        transition_workflow(tmp_path, workflow.id, "implementing")


def test_high_risk_workflow_rejects_self_approved_review(tmp_path):
    workflow = start_workflow(tmp_path, "Change authentication", mode="high-risk", workflow_id="independent-review")
    _to_verification(tmp_path, workflow.id)
    record_verification(tmp_path, workflow.id, "tests", passed=True, by="tester")
    transition_workflow(tmp_path, workflow.id, "review")
    record_artifact(tmp_path, workflow.id, "review", "self approved", status="approved", by="implementer")

    with pytest.raises(ValueError, match="other than the implementer"):
        transition_workflow(tmp_path, workflow.id, "complete")


def test_manual_verification_cannot_pass_a_workflow_gate(tmp_path):
    workflow = start_workflow(tmp_path, "Fix auth", workflow_id="manual-verification")
    _to_verification(tmp_path, workflow.id)
    record_verification(tmp_path, workflow.id, "agent says green", passed=True, evidence="manual")

    with pytest.raises(ValueError, match="passed verification"):
        transition_workflow(tmp_path, workflow.id, "review")


def test_executed_verification_records_output_digests_not_raw_output(tmp_path):
    workflow = start_workflow(tmp_path, "Fix auth", workflow_id="verified-output")
    result = VerificationResult([CommandResult("pytest", 0, "token=do-not-store", "", 0.123)])

    recorded = record_execution_verification(tmp_path, workflow.id, result, by="tester")
    artifact = recorded.artifacts[-1]

    assert artifact.evidence == "executed"
    assert artifact.status == "passed"
    assert "token=do-not-store" not in artifact.value
    assert "stdout_sha256" in artifact.value


def test_blocked_workflow_can_resume_without_losing_history(tmp_path):
    workflow = start_workflow(tmp_path, "x", workflow_id="blocked")
    transition_workflow(tmp_path, workflow.id, "blocked", note="Need API decision")
    resumed = transition_workflow(tmp_path, workflow.id, "context_ready", note="Decision received")

    assert resumed.state == "context_ready"
    assert [event.to_state for event in resumed.history] == ["intake", "blocked", "context_ready"]


def test_workflow_requires_fresh_verification_and_review_after_new_implementation(tmp_path):
    workflow = start_workflow(tmp_path, "Fix auth", workflow_id="fresh-evidence")
    _to_verification(tmp_path, workflow.id)
    record_verification(tmp_path, workflow.id, "first test run", passed=True)
    transition_workflow(tmp_path, workflow.id, "review")
    record_artifact(tmp_path, workflow.id, "review", "first review", status="approved")

    # A change after both artifacts invalidates them for completion.
    record_artifact(tmp_path, workflow.id, "implementation", "follow-up change")
    with pytest.raises(ValueError, match="latest implementation"):
        transition_workflow(tmp_path, workflow.id, "complete")

    record_verification(tmp_path, workflow.id, "second test run", passed=True)
    with pytest.raises(ValueError, match="approved review after"):
        transition_workflow(tmp_path, workflow.id, "complete")

    record_artifact(tmp_path, workflow.id, "review", "second review", status="approved")
    assert transition_workflow(tmp_path, workflow.id, "complete").state == "complete"
