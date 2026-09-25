---
name: caching-added-for-cheap-computation-adds-risk-no-benefit
description: A cache layer was added in front of a computation or lookup that was already fast and cheap, adding staleness bugs and a new outage mode for negligible measured performance gain.
triggers: ["should we cache this even though it's already fast", "do we really need a cache here", "this cache barely saves any time but causes stale data bugs", "removing a cache that doesn't seem to help"]
permissions: ["READ"]
---

## Symptom
A cache sits in front of an operation — a database lookup on an indexed primary key, a small in-memory computation, a call to a service with single-digit-millisecond latency — and the team spends recurring effort dealing with its side effects: stale-data bug reports, cache-unavailability handling, extra monitoring, and invalidation logic to maintain, while nobody can point to a specific latency or load number that justifies its existence. When the cache is temporarily disabled or bypassed for debugging, overall system performance is unaffected or barely measurable.

## Likely causes
1. **Caching was applied by default/habit** ("we cache database reads" as a blanket policy) rather than in response to a measured bottleneck, so it was added to operations that were never actually slow or expensive.
2. **The underlying operation got faster after the cache was added** (a new index, a schema change, a faster underlying service) but the cache was never revisited, so it's now protecting against a cost that no longer exists.
3. **The "expensive" operation being cached is actually dominated by something else in the request** (network round-trip, serialization, an unrelated slow call earlier in the chain), so caching it shaves microseconds off a request that's slow for entirely different reasons — the cache never could have moved the needle.
4. **Cache overhead (network hop to an external cache, serialization/deserialization, key construction) is comparable to or larger than the cost of just recomputing/refetching**, especially for small, cheap values where the cache call itself is the more expensive operation.
5. **The cache was justified by anticipated future scale that never materialized** — added preemptively "for when we have more traffic," carrying complexity cost in the present for a benefit that may never arrive or may arrive needing a different design anyway.

## Diagnose
1. Measure the actual latency/cost of the underlying operation without the cache — run it directly (a raw query with `EXPLAIN ANALYZE`, a direct timed call to the uncached function) under realistic conditions, and compare against the cache lookup's own latency (including network hop if it's an external cache like Redis/Memcached).
2. Check whether the operation being cached is on an indexed, primary-key-style lookup path or already backed by a database's own buffer cache/query cache — if so, the marginal benefit of an application-level cache on top is often small.
3. Look at the cache's own hit-rate and time-saved metrics if they exist; if they don't exist, that absence is itself a signal this cache was never held accountable to a performance goal (see the separate skill on missing hit-rate monitoring).
4. Temporarily bypass the cache in a staging or canary environment under representative load and compare end-to-end request latency and backing-store load with and without it — a negligible difference is the direct answer to whether it's earning its keep.
5. Count the number of stale-data bug reports, on-call pages, or code-review comments attributable to this specific cache's invalidation logic over the last few months, and weigh that maintenance cost against the measured performance number from step 1.

## Fix
Require a measured baseline before adding a cache: profile the operation, establish it actually costs enough (in latency, backing-store load, or external API rate-limit/cost) to justify the complexity, and set an explicit target (e.g., "reduce p95 from 200ms to 20ms" or "cut DB QPS on this table by 80%") that the cache is expected to hit. For an existing cache that can't demonstrate this, remove it — deleting a cache is a legitimate, often underused simplification: fewer invalidation bugs, one less failure mode (cache unavailable/full), and simpler reasoning about consistency, in exchange for a cost you've confirmed is negligible. If there's genuine uncertainty, remove it behind a flag or in a canary and watch the real metrics rather than debating it.

## Pitfalls
Don't justify keeping a low-value cache with "it can't hurt" — every cache is a second copy of truth that can drift, a dependency that can fail independently of the backing store, and a piece of code someone has to maintain and reason about during incidents; "can't hurt" is rarely actually true once on-call cost is counted. Conversely, when removing a cache, don't remove it silently without checking whether something downstream depends on it for reasons beyond raw performance (e.g., it happens to be shielding a rate-limited third-party API, or a batch job briefly spikes load in a way the cache smooths over) — verify the "cheap" classification holds under peak/burst conditions, not just steady-state average load.

## Verify
After removing or declining to add the cache, monitor the backing store's load (query latency percentiles, QPS, CPU) and the endpoint's end-to-end latency across at least one full peak-traffic cycle (e.g., a business day or a known high-traffic window); confirm both stay within acceptable bounds with no cache in place, and confirm the stale-data bug category for this data path drops to zero going forward.
