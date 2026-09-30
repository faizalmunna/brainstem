---
name: workflow-start
description: Start a durable, right-sized engineering workflow before a coding task loses its plan, context, or evidence across agent sessions.
triggers: ["start feature", "implement feature", "fix bug", "make a change", "workflow"]
permissions: ["READ", "WRITE"]
---

# Workflow Start

Before changing code, call `start_workflow(task, mode)`.

- Use `fast` for a small, low-risk correction with a narrow test.
- Use `standard` for a feature, refactor, or ordinary bug fix.
- Use `high-risk` for authentication, payments, secrets, production infrastructure, destructive data work, or deployment.

Call `query_context` and `get_rules`, then record a short `context` artifact.
For standard and high-risk work, record an approved `design` before planning.
For high-risk work, also record an approved `threat_review` before planning.

Use `get_next_work_item` after every state transition. Do not paste entire
transcripts into the workflow; store paths or concise evidence summaries.
