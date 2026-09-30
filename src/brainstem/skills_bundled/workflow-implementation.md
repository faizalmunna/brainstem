---
name: workflow-implementation
description: Keep an in-progress coding task bounded by its approved plan and preserve implementation evidence before verification or review.
triggers: ["implement plan", "start coding", "write code", "continue implementation", "workflow implementing"]
permissions: ["READ", "WRITE"]
---

# Workflow Implementation

Read `get_next_work_item` before starting a task. Work only on the smallest
approved plan item; if the design changes materially, return to design review
instead of silently expanding scope.

Before entering `implementing`, record a `plan` artifact with the task and
test approach. When the bounded change is ready, record an `implementation`
artifact listing changed files and any important limitation.

Run deterministic tests through the host or `run_verification`. Record the
exact command and concise pass/fail output with
`record_workflow_verification`. A failed check returns to implementation; it
is never proof of completion.
