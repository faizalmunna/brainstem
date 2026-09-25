---
name: dead-letter-queue-silent-accumulation
description: The dead-letter queue has grown for days or weeks with failed jobs and nobody noticed because nothing monitors its depth or age.
triggers: ["dead letter queue full", "DLQ growing unnoticed", "failed jobs never reprocessed", "nobody was watching the DLQ", "dlq depth alert missing"]
permissions: ["READ"]
---

## Symptom
The dead-letter queue (DLQ) or failed-job table has quietly accumulated a large number of entries over an extended period, discovered by accident (manually opening the broker console, or a downstream side effect of the backlog) rather than through any alert, with no one having triaged or reprocessed the failures during that time.

## Likely causes
1. **The DLQ was configured as part of the original retry design but no metric or alert was ever attached to its depth** -- it was built as a safety net for individual jobs, not as an operational signal that needs its own monitoring.
2. **The DLQ mixes transient failures that would have eventually succeeded with genuinely permanent ones**, and with no triage process it grows large enough that reviewing it feels daunting, which discourages ever starting.
3. **Alerting exists for the main processing queues' depth but was never extended to the DLQ**, since it's a structurally different queue/table that was never wired into the "is the system keeping up" dashboard.
4. **DLQ entries carry the original payload but no failure context** (no reason, no stack trace, no attempt count), so even when someone does look, individual entries aren't actionable without re-deriving the failure, which further discourages regular review.

## Diagnose
- Check whether any existing alert or dashboard panel references the DLQ's depth or the age of its oldest entry at all -- confirm the absence first, rather than assuming a threshold is just misconfigured.
- Query current DLQ depth and the age of the oldest unprocessed entry, then sample a handful of entries to categorize failure reasons (bug, bad input, expired dependency, transient outage that was never retried) and gauge whether it's actionable as-is.
- Check what metadata is captured per entry -- original payload, failure reason, timestamp, attempts exhausted -- versus what would actually be needed to triage without re-running the job in a debugger.

## Fix
Add an alert on DLQ depth (an absolute threshold and/or rate of growth) and on the age of its oldest unacknowledged entry, routed to the same on-call rotation as other production alerts, not a passive dashboard panel. Establish an explicit triage cadence and owner, even a lightweight weekly review, since a DLQ with no attached process will silently grow regardless of how good the alerting is. Capture failure context at the point of dead-lettering -- the original payload, the exception message/stack trace, the final-failure timestamp, and the number of attempts made -- enough for someone to triage without re-deriving the failure from scratch. Build (and periodically exercise) a reprocessing path -- a script or admin action that replays some or all entries back into the main queue once a fix ships -- so triage has a concrete next step beyond acknowledging and deleting.

## Pitfalls
Alerting on every single arrival into the DLQ, rather than on depth/age thresholds, produces noise that gets muted quickly -- alert on accumulation trends and staleness, not each individual entry landing there. Building a reprocessing tool once and never testing it against the DLQ's current schema means it silently breaks the first time it's actually needed, since the payload format may have drifted since the tool was written -- exercise it periodically, not only at build time.

## Verify
Force a job to fail through its full retry budget in staging and confirm it lands in the DLQ with complete failure context, that the depth/age alert fires against a temporarily lowered threshold and reaches the correct on-call channel, and that the reprocessing path successfully replays that specific entry back into the main queue.
