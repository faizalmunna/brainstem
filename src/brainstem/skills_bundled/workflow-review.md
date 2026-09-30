---
name: workflow-review
description: Prevent a coding task from being marked complete without passing verification and an independent, explicit review decision.
triggers: ["review change", "code review", "finish task", "complete workflow", "ready to merge"]
permissions: ["READ", "WRITE"]
---

# Workflow Review

Enter review only after a passed `verification` artifact exists. Review the
diff against the recorded design and plan, then check correctness, tests,
security impact, scope creep, and user-visible behavior.

Record a `review` artifact with status `approved` only when there are no
blocking findings. Record findings concisely and return the workflow to
`implementing` when changes are needed. The implementer must not approve its
own high-risk permission escalation or deployment.

Transition to `complete` only after both passed verification and approved
review are recorded. Then capture a reusable decision or skill outcome when
it would prevent future agents from repeating the same work.
