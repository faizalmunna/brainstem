---
name: retry-storm-during-downstream-outage-recovery
description: A downstream dependency that just recovered from an outage gets immediately hit with a much larger traffic spike than normal because every job retrying against it fires back at once.
triggers: ["thundering herd after outage", "downstream service fell over right after recovering", "retry storm on recovery", "queue backlog crushes service after it comes back up"]
permissions: ["READ"]
---

## Symptom
A downstream dependency (a database, a third-party API, an internal service) has an outage; queue-backed jobs calling it fail and retry throughout. The moment the dependency comes back online, it receives a burst of traffic several times its normal steady-state load -- sometimes enough to knock it back down right after it recovered.

## Likely causes
1. **No jitter in the retry backoff**, so jobs that failed around the same time (which, during a shared outage, is most of them) compute nearly identical retry delays and their retry attempts land back in the same narrow window, synchronizing into a wave the instant the dependency responds again.
2. **Queue depth grew substantially during the outage** because producers kept enqueueing at normal rate while consumption stalled, so recovery means draining both the accumulated backlog *and* newly arriving jobs simultaneously, at several times the dependency's steady-state capacity.
3. **No circuit breaker at the job-handler level**, so every worker keeps attempting the call at full configured concurrency throughout the outage instead of the system collectively backing off, and that same full concurrency floods in the instant calls start succeeding.
4. **Backoff has a jitter ratio too small relative to the interval**, so even independently-scheduled retries drift back into alignment after a few cycles rather than staying desynchronized.

## Diagnose
- Reconstruct the timeline: outage start/end, queue depth growth during the outage, and the dependency's own inbound request-rate metric right at and after the recovery timestamp -- look specifically for a sharp spike rather than a ramp.
- Check the retry/backoff configuration for actual jitter: compare a fixed exponential sequence (1s/2s/4s/8s, identical for every failing job) against a jittered version (`base * 2^n * random(0.5, 1.5)`).
- Check whether worker concurrency for the affected call is throttled based on the dependency's live error rate (a circuit breaker or adaptive limiter) or stays at full configured concurrency regardless of downstream health.

## Fix
Add jitter to every retry backoff calculation, not just the base exponential curve, so retries from different jobs desynchronize instead of clustering into waves. Put a circuit breaker (or a shared rate limiter/semaphore, coordinated across worker processes, not per-process) around the specific downstream call, tripping during sustained failures and allowing only a small trickle of probe requests through to detect recovery, then ramping concurrency back up gradually instead of releasing the full backlog the instant one probe succeeds. For a large backlog specifically, route retried jobs through a separate, lower-concurrency consumer so backlog drain after an outage is rate-limited independently of normal new-job throughput.

## Pitfalls
A circuit breaker with no half-open/probe ramp either stays fully closed too long (delaying legitimate recovery detection) or snaps fully open the instant one probe succeeds, recreating the exact spike it was meant to prevent -- use a gradual token-bucket-style ramp, not a binary switch. Jitter alone doesn't fix a backlog that's simply larger than the dependency's recovered capacity -- it needs to be paired with concurrency throttling during drain, not treated as the only lever.

## Verify
Simulate a downstream outage in staging (block the dependency for a fixed window while jobs keep arriving and failing), then restore it and graph the dependency's incoming request rate across the recovery moment -- confirm it ramps up gradually toward steady-state rather than spiking to several times normal load in the first seconds after recovery.
