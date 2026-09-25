---
name: job-result-lost-ttl-expired
description: A caller polling for a background job's result gets a not-found response even though the job completed successfully, because the result backend's entry expired first.
triggers: ["job result not found but it succeeded", "celery result expired", "polling for task status returns nothing", "bullmq job result missing", "result backend TTL too short"]
permissions: ["READ"]
---

## Symptom
Code that enqueues a job and later polls for its result -- or a user-facing status page checking completion -- gets an empty/not-found result even though the job actually ran and completed successfully, traced to the result backend having evicted or expired the entry before it was read.

## Likely causes
1. **The result backend's TTL is shorter than the realistic delay between job completion and the caller actually checking** (Celery `result_expires`, a Redis key TTL, BullMQ `removeOnComplete`) -- an infrequent poller, a slow client, or a batched UI check can lose the race even under a "reasonable-looking" default.
2. **The result backend evicts under memory pressure independent of the configured TTL** -- Redis with `maxmemory-policy` set to an eviction mode like `allkeys-lru` will evict keys early under load, regardless of their nominal expiry.
3. **The caller treats a missing result as equivalent to job failure or nonexistence**, with no distinct "expired/unknown" case, so an expired-but-successful job gets misreported to the end user as an error.
4. **Job chaining/fan-out where a downstream job depends on an upstream job's result**, and scheduling delays or a queue backlog push the downstream read past the upstream result's TTL, since the two jobs aren't otherwise coupled with a direct handoff.

## Diagnose
- Compare the configured result TTL against measured real-world "time from job completion to caller check," including the tail (p99, not just the median) -- log both timestamps and compute the actual distribution.
- Check the result backend's eviction policy and current memory pressure metrics; for Redis specifically, check `maxmemory-policy` -- an `allkeys-lru`/`allkeys-lfu` setting evicts under memory pressure before TTL expiry.
- Reproduce directly: enqueue a job, wait past the configured TTL, then query its result through the real code path and confirm the not-found behavior, ruling out an unrelated bug being mistaken for TTL expiry.

## Fix
Set the result TTL based on measured caller-check latency including its tail, with real margin, rather than leaving whatever default the framework ships with. For results that must not be lost regardless of polling delay, don't rely on an ephemeral/TTL'd backend as the source of truth at all -- persist completion status and result payload in a durable store (a database row) that the caller reads, treating the fast/ephemeral backend as an optional optimization layer if used at all. If Redis is the result backend, exclude result keys from LRU/LFU eviction (a dedicated instance or logical DB with `noeviction`, or excluded namespacing) so results aren't evicted early under a load spike. Make the caller explicitly distinguish "result expired/unknown" from "job failed" from "job doesn't exist" in its response/UI, and where feasible re-derive status from the durable source when the fast-path result is missing.

## Pitfalls
Setting the TTL very large "to be safe" trades a rare lost-result bug for permanently growing result-backend memory usage -- pair a longer TTL with a deliberate decision about what's retained and why, especially for high-volume job types. Adding a durable database write for completion status but treating it as equivalent effort to the fast-path write, and skipping verification under time pressure, just relocates the same bug to a different, less obvious condition -- confirm the durable write actually happens synchronously before the job is considered complete.

## Verify
Enqueue a job, deliberately wait past the configured result TTL (or trigger simulated memory pressure on the result backend), then query the result through the same code path the real caller uses and confirm it returns a clearly-distinguished "expired/unknown" state rather than being misreported as failure, with a durable-store lookup (if implemented) still returning the correct completion status.
