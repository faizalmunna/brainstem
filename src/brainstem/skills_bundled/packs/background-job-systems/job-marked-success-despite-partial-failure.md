---
name: job-marked-success-despite-partial-failure
description: A background job's status shows completed successfully even though the job only performed part of its intended work before an internal step failed.
triggers: ["job shows success but data is wrong", "task marked done but didn't finish", "partial failure not reflected in job status", "celery task returns success incorrectly"]
permissions: ["READ"]
---

## Symptom
A job's status field, dashboard, or result backend reports success, but a data audit or user report reveals the job only completed some of its intended steps -- some records updated but not others, a downstream call never made, a notification never sent -- and there was no failed-job alert to catch it.

## Likely causes
1. **An exception from a later step is caught and the function still reaches a `return`/success path**, often because a broad `try/except` was added around the whole job body to "prevent it from failing" without distinguishing which steps are actually required for correctness.
2. **A multi-step job body isn't transactional or checkpointed** -- an early step commits durably, a later step throws, but nothing tracks that only the first step actually finished, and the framework only sees "the function didn't raise" or a caught-and-swallowed exception.
3. **Fire-and-forget sub-calls inside the job** (an external API call whose response status is never checked, a downstream enqueue that isn't confirmed) whose failure never propagates into the outer job's return/exception path at all.
4. **The result backend only records whatever the task function returns**, and an except block has a bare `return` or a default success value instead of re-raising, making the failure structurally invisible to any dashboard built on that result field.

## Diagnose
- Read every except/rescue block in the job body and trace control flow: does an exception from a required step end execution and mark failure, or get swallowed with execution continuing to a success return?
- Compare "jobs marked successful" counts against an independent downstream count that should move in lockstep (rows actually updated, emails the provider's API confirms as sent) to detect the gap directly rather than by inspection alone.
- Check whether the job performs multiple independent side effects with no per-step progress recorded -- if it crashed between steps, is there any way, for a given job id, to tell which steps actually ran?

## Fix
Structure the job so each required side effect either fully completes or the job explicitly re-raises/records failure -- never catch an exception from a required step and continue silently to a success return. For jobs with multiple steps that aren't naturally transactional, record per-step progress (a status field per step, or split the work into separate chained jobs) so a partial failure is both visible and resumable, rather than relying on one atomic "did the function throw" signal covering the whole thing. Where a step is genuinely optional and best-effort (a non-critical analytics ping), make that explicit with its own narrow catch and a low-severity log, kept separate from the catch path used for steps whose failure should actually fail the job.

## Pitfalls
Overcorrecting into a blanket try/except around the whole body that logs and re-raises everything turns genuinely optional side effects into hard failures that now retry forever -- apply re-raise selectively, only to steps whose failure should actually fail the job. Adding a granular per-step status field but never having anything query it (no dashboard, no alert) reproduces the same invisibility one layer down.

## Verify
In a test or staging run, deliberately make one non-first step of the job fail and confirm the job's final recorded status reflects failure (not success), and that a status/audit query can identify exactly which step failed for that specific job id.
