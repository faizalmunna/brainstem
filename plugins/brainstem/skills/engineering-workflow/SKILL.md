---
name: engineering-workflow
description: Use when starting or continuing a software change that needs durable design, test, verification, and review evidence.
---

Use Brainstem as the durable workflow ledger; do not replace it with a long
chat transcript.

1. Start a `standard` workflow for ordinary changes; use `high-risk` for
   permission, dependency, network, secret, installation, deployment, or
   destructive changes. Use `fast` only for a narrow, low-risk fix.
2. Retrieve a bounded context bundle before design. Record a concise context
   artifact naming the relevant files and constraints.
3. For standard/high-risk work, record an approved design, implementation
   plan, and test plan before implementation.
4. Record implementation evidence as changed files or a compact diff digest.
   Never put credentials, full command output, or a long transcript into an
   artifact.
5. Use `run_workflow_verification`, or the `brainstem workflow verify-run`
   CLI command, for gate-satisfying verification. A manually recorded green
   result is an attestation only and cannot pass the gate.
6. Request independent review before completion. For high-risk work, the
   reviewer must not be the implementation author.

Use `get_next_work_item` after every transition. It is the current source of
truth for the next role and required evidence.

Never enable broad execution or add lifecycle hooks to bypass these gates.
