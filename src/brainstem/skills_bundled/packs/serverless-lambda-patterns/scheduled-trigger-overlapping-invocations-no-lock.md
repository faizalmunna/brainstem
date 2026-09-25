---
name: scheduled-trigger-overlapping-invocations-no-lock
description: A time-scheduled function invocation overlaps with a still-running previous invocation because no mutual-exclusion mechanism prevents concurrent runs.
triggers: ["scheduled lambda running twice", "cron function overlapping executions", "cloudwatch events triggering duplicate runs", "scheduled function race condition"]
permissions: ["READ"]
---

## Symptom
A function triggered on a fixed schedule (EventBridge Scheduler/Rules, a
timer trigger in Azure Functions, a Cloud Scheduler job) is meant to run
one job to completion before the next scheduled tick fires, but under
certain conditions -- the job runs longer than usual, a downstream
dependency is slow, or a redeploy happens mid-run -- two invocations end
up executing concurrently. This produces duplicated work (the same batch
processed twice), inconsistent results (both invocations racing to update
the same record), or resource contention (both invocations competing for
the same limited downstream connections/capacity) that only appears
intermittently, exactly when a run happens to take longer than the
schedule's interval.

## Likely causes
1. **The schedule interval assumes a fixed, short run time that isn't
   actually guaranteed** -- the job's duration depends on variable
   downstream data volume or dependency latency, so on a normal day it
   finishes well within the interval, but on a slow day it's still
   running when the next scheduled invocation fires, and nothing in the
   architecture prevents that overlap.
2. **No mutual-exclusion mechanism exists at all** -- the scheduler
   simply fires on time regardless of whether a previous invocation
   completed, because the team assumed "it always finishes in time" as an
   implicit invariant rather than an enforced one, and platforms
   generally don't serialize scheduled invocations for you by default.
3. **A redeploy or configuration change happens to coincide with a
   scheduled firing**, so the in-flight invocation on the old code version
   and a new invocation (possibly on updated code) both run against the
   same shared state simultaneously, which is a narrower but real version
   of the same overlap problem.
4. **An existing lock mechanism has a bug that lets it fail open** -- a
   lock record with a TTL that expires while the job is still legitimately
   running (because the TTL was sized for the typical case, not the worst
   case) causes the lock to be considered released and a second
   invocation acquires it while the first is still active.
5. **Manual/ad hoc invocations of the same function** (a developer testing
   against production, or a retry triggered by an on-call engineer)
   happen to coincide with a scheduled firing, and because there's no
   single mutual-exclusion point covering all invocation sources, the
   manual trigger and the scheduled one collide.

## Diagnose
- Compare the job's actual measured duration distribution (not just the
  typical/median case) against the schedule's configured interval -- if
  p95 or max duration approaches or exceeds the interval, overlap is not
  a hypothetical risk but a near-certainty under realistic conditions.
- Grep logs for two invocation IDs with overlapping start/end timestamps
  for the same scheduled function -- this directly confirms overlap
  occurred, as opposed to inferring it from downstream symptoms alone.
- If a lock mechanism exists, check its TTL/lease duration against the
  job's actual worst-case duration, and check logs for cases where the
  lock was acquired by a second invocation while log evidence shows the
  first invocation was still actively running -- indicates the TTL is
  too short for the real worst case.
- Check whether downstream side effects show evidence of double
  processing (a count that's roughly double the expected daily volume, a
  duplicate-key constraint violation logged and silently caught) which
  can indicate overlapping runs even when no explicit lock-related error
  was logged.
- Review deploy history timestamps against the schedule to check whether
  any known overlap incident coincided with a deployment, narrowing
  whether the cause is pure duration variance or specifically
  deploy-triggered.

## Fix
Add an explicit mutual-exclusion mechanism rather than relying on the
schedule interval being longer than the job ever takes: use a
conditional/atomic write to a lock record (a DynamoDB item with a
conditional put, a database row with an advisory lock) that the
invocation must acquire before doing work and release when done, with a
lease TTL sized generously above the job's true worst-case duration (not
its median) so the lock can't expire out from under a still-legitimately-
running job. Make the job itself idempotent wherever feasible (safe to
run twice without duplicating effects) as defense in depth, since a lock
mechanism reduces but doesn't guarantee zero overlap (a crash between
acquiring the lock and releasing it, for instance). For platforms that
support it, consider whether the workload is better modeled as a
long-running consumer (pulling from a queue continuously) than a
fixed-interval trigger, which sidesteps the "does it finish before the
next tick" question entirely.

## Pitfalls
Adding a lock but sizing its TTL from the job's typical duration rather
than its worst-case duration just relocates the bug: the lock will expire
and let a second invocation start while the first is still legitimately
running exactly on the days when duration is unusually long, which is
precisely when overlap-caused problems are most likely. Also, a lock
implemented as a simple existence-check-then-write (rather than an atomic
conditional write) has its own race condition where two invocations can
both check, both see no lock, and both proceed -- the acquire step itself
must be atomic, not just present.

## Verify
Deliberately extend the job's duration in a test environment (via an
injected delay) to exceed the schedule interval, let two scheduled
firings occur during that window, and confirm only one invocation
actually performs the work while the second either waits, is skipped, or
exits early having detected the lock -- with no duplicated downstream
side effects from the overlapping firing.
