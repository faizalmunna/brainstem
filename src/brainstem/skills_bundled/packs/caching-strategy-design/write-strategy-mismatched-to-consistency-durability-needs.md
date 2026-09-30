---
name: write-strategy-mismatched-to-consistency-durability-needs
description: A write-through, write-around, or write-back caching strategy was chosen without weighing its specific consistency and durability tradeoffs against the use case, causing unexpected data loss or staleness.
triggers: ["we lost writes when the cache node restarted", "should we use write-through or write-back for this", "data written to the cache never made it to the database", "choosing a cache write strategy"]
permissions: ["READ"]
---

## Symptom
One of several patterns shows up depending on which write strategy was picked without analysis. With write-back (write to cache, flush to backing store asynchronously later): a cache node crash or restart loses writes that were acknowledged to the client but never made it to durable storage. With write-around (write goes straight to the backing store, bypassing the cache): reads immediately after a write are cache misses that then populate the cache with a fresh read, which is fine for durability but means a naive read-through right after write looks "slow" or, worse, a stale cached copy from before the write lingers if invalidation wasn't also handled. With write-through (write goes to cache and backing store synchronously): writes are slower than expected because every write now pays the latency of two systems, and nobody budgeted for that.

## Likely causes
1. **The strategy was chosen based on a tutorial or another team's setup** for a different use case (e.g., copying a write-back pattern used for a metrics/analytics pipeline, where losing a few data points is fine, into a path handling financial or user-account data, where it isn't).
2. **Durability requirements were never stated explicitly** — nobody asked "if this cache node dies right now, which writes are we OK losing," so the strategy's actual data-loss window was never sized against an acceptable answer.
3. **Write latency budget wasn't considered** — write-through was picked for its consistency guarantees without accounting for the added latency of a synchronous dual write, which then fails a separate, unrelated SLA on write endpoint response time.
4. **Read and write paths were designed by different people at different times**, so the write strategy and the read/invalidation strategy don't actually compose correctly (e.g., write-around without also invalidating or bypassing any existing cached entry for that key leaves stale data readable until TTL expiry, defeating the durability benefit write-around was chosen for).
5. **The strategy was never revisited when the use case's criticality changed** — a feature that started as a nice-to-have (write-back is fine) became business-critical (needs write-through or at least a durable write-back queue) without a corresponding review of the caching strategy.

## Diagnose
1. State explicitly, for the data in question, what happens if a write is lost entirely versus merely delayed — is this financial/transactional data where loss is unacceptable, or ephemeral/regenerable data (a view counter, a recommendation score) where loss is a shrug? This single question usually reveals whether the current strategy is a mismatch.
2. For write-back specifically, check whether the async flush-to-backing-store queue is itself durable (e.g., backed by a persistent queue or WAL) or purely in-memory in the cache node — an in-memory flush queue on a cache node that restarts is a guaranteed loss window, not just a risk.
3. Measure current write-path latency broken down by segment (cache write time vs. backing-store write time) to see whether a write-through's dual-write cost is actually within the endpoint's latency budget or silently blowing through it.
4. Trace a single write end-to-end for the current strategy and confirm what a read immediately after that write returns, from a client that didn't perform the write — this exposes whether the read/invalidation side is actually coherent with the chosen write strategy.
5. Check incident history for this data path for "write succeeded but data missing" or "write took much longer than expected" reports, and correlate timing with cache node restarts/deploys if write-back is in use.

## Fix
Choose the write strategy from the durability and latency requirements, not the other way around: use write-through when reads must reflect writes immediately and losing an acknowledged write is unacceptable, accepting the added write latency as the cost. Use write-back only when some bounded write loss is genuinely tolerable (regenerable or low-value data) or when the flush queue itself is made durable (persisted, replicated) so a cache node failure doesn't equal data loss — treat "write-back with a durable queue" and "write-back with an in-memory queue" as two entirely different risk profiles, not the same strategy. Use write-around when writes are much more frequent than reads for the same data (so populating the cache on every write would mostly cache things nobody re-reads), pairing it with active invalidation of any existing cache entry for that key so a stale pre-write value can't still be served.

## Pitfalls
Don't assume "we use a distributed cache so write-back is durable enough" — replication across cache nodes protects against a single node failure but not against a correlated failure (a bad deploy, a cluster-wide restart, an OOM cascade) unless the durability was explicitly verified for that failure mode. Also don't mix strategies inconsistently across code paths that write the same data (one write path uses write-through, a batch job writes directly to the backing store using write-around) without ensuring both paths handle invalidation, or the strategy that looks correct in isolation gets undermined by the other path's stale cache entries.

## Verify
Simulate the specific failure mode the chosen strategy is supposed to tolerate: for write-back, kill the cache node (or the process) immediately after a write is acknowledged and confirm whether the write is present in the backing store afterward, matching the documented, accepted loss window (zero, or a bounded number of seconds) — not "however much happened to be in flight." For write-through, load-test the write endpoint and confirm p99 write latency stays within its stated SLA with the dual write in place.
