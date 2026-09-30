import json

from brainstem.audit import audit_path, record_audit
from brainstem.workflow import record_artifact, start_workflow


def test_audit_redacts_detail_and_writes_jsonl(tmp_path):
    event = record_audit(
        tmp_path, action="workflow.test", actor="reviewer", outcome="allowed", detail="api_key=not-for-log"
    )

    line = audit_path(tmp_path).read_text(encoding="utf-8")

    assert "api_key=not-for-log" not in line
    assert json.loads(line) == event
    assert len(event["detail_sha256"]) == 64


def test_workflow_mutations_emit_redacted_audit_events(tmp_path):
    workflow = start_workflow(tmp_path, "Do not store this task literally", workflow_id="audited")
    record_artifact(tmp_path, workflow.id, "plan", "secret implementation text", by="planner")

    log = audit_path(tmp_path).read_text(encoding="utf-8")

    assert "Do not store this task literally" not in log
    assert "secret implementation text" not in log
    assert '"action":"workflow.start"' in log
    assert '"action":"workflow.artifact"' in log
