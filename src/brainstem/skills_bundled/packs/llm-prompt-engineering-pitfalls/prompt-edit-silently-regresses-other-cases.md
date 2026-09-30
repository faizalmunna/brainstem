---
name: prompt-edit-silently-regresses-other-cases
description: A quick wording fix to a shared prompt template silently breaks behavior for other use cases that depended on the previous wording, with no test to catch it.
triggers: ["fixed one thing in the prompt and broke another feature", "prompt change regressed a different flow", "nobody noticed the prompt edit broke something until a user complained", "prompt isn't version controlled and someone edited it in production"]
permissions: ["READ"]
---

## Symptom
Someone edits a shared prompt template to fix a specific reported issue (e.g. "the assistant is too verbose for support tickets"), ships the change, and the immediate issue is resolved -- but days or weeks later, a different feature or user segment that shares the same underlying prompt template starts behaving differently in a way nobody connects back to that edit, because there was no test suite or review process that would have caught the cross-impact before shipping.

## Likely causes
1. **The prompt template is treated as configuration/content rather than code** -- edited directly (in a dashboard, a config file, or inline in application code) without going through the same review, testing, and versioning discipline as a code change, even though it has equivalent behavioral impact.
2. **A single prompt template is shared across multiple distinct use cases** with no per-use-case regression coverage, so a change validated against the one use case that prompted the edit has no safety net for the others quietly depending on the same wording.
3. **No prompt-level test/eval suite exists at all**, or one exists but isn't run as part of the change process, so there's no automated signal that a change altered behavior outside its intended scope.
4. **No diff/changelog visibility into prompt changes** -- if the prompt lives outside version control (e.g. edited directly in a hosted prompt-management UI or a database row), there may be no record of what changed, when, or why, making the eventual regression hard to even trace back to a cause.
5. **The person making the "quick fix" doesn't know about the other use cases** sharing the template, because prompt ownership and its consumers aren't documented anywhere discoverable.

## Diagnose
- When a regression is reported, check the prompt template's edit history (if version-controlled) for recent changes and their timestamps, and cross-reference against when the regression started -- if there's no version history at all, that absence is itself the root-cause finding.
- Identify every call site / feature that uses the affected prompt template, since the fix that caused the regression was very likely validated against only one of them.
- If an eval suite exists, check whether it was actually run against the change before it shipped, and whether it has coverage for the use case that regressed.
- Diff the current prompt wording against the last known-good version (from history, backups, or logs of past requests) to identify exactly what changed and reason about which behaviors that specific wording change would plausibly affect.

## Fix
Treat prompt templates as code: store them in version control, require the same review process as a code change (a diff that reviewers can read and reason about), and never edit them directly in a production system without going through that path. Maintain an eval/regression suite that covers every distinct use case sharing a template, and require it to run and pass before a prompt change ships -- the suite is what turns "I fixed my one case" into "I confirmed I didn't break the others." Where use cases have diverged enough that a shared template creates this recurring risk, consider splitting into separate, purpose-specific templates with their own smaller shared core, rather than continuing to overload one template for unrelated needs.

## Pitfalls
Adding version control for prompts but still allowing changes to ship without running the eval suite (treating the review as sufficient on its own) leaves the actual gap unaddressed -- human review reliably catches wording issues but rarely predicts second-order behavioral shifts across every downstream use case the way an automated eval run does.

## Verify
After introducing versioning and an eval suite, make a deliberate small wording change to a shared template in a test environment and confirm the eval suite actually fails for a use case it wasn't intended to affect (a canary test of the safety net itself), then confirm the real fix passes eval across all known use cases before merging.
