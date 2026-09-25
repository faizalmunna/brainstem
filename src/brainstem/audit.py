"""Append-only, redacted local audit events.

Audit records are intentionally small and contain a SHA-256 digest of detail
instead of raw prompts, source excerpts, command output, or possible secrets.
They make security-sensitive workflow changes explainable without creating a
second sensitive data store.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from .manifest import brain_dir

AUDIT_DIRNAME = "audit"


def audit_path(repo_root: Path) -> Path:
    return brain_dir(repo_root) / AUDIT_DIRNAME / "events.jsonl"


def record_audit(
    repo_root: Path,
    *,
    action: str,
    actor: str,
    outcome: str,
    workflow_id: str | None = None,
    detail: str = "",
) -> dict:
    """Write one redacted event and return its structured representation."""
    if not action or not actor or not outcome:
        raise ValueError("Audit action, actor, and outcome cannot be empty.")
    if len(action) > 100 or len(actor) > 128 or len(outcome) > 64 or len(detail) > 16_000:
        raise ValueError("Audit event field exceeds its maximum length.")
    event = {
        "at": datetime.now(UTC).isoformat(),
        "action": action,
        "actor": actor,
        "outcome": outcome,
        "workflow_id": workflow_id,
        "detail_sha256": hashlib.sha256(detail.encode("utf-8")).hexdigest(),
    }
    path = audit_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    return event
