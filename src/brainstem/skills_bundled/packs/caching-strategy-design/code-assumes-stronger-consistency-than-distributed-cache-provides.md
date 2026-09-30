---
name: code-assumes-stronger-consistency-than-distributed-cache-provides
description: Application code was written as if a distributed cache guarantees immediate consistency across all nodes, but the cache's actual replication model allows different nodes to briefly disagree.
triggers: ["different servers are returning different cached values for the same key", "we invalidated the cache but some requests still see the old value", "read from one cache node doesn't match another node's value", "cache replication lag causing inconsistent behavior"]
permissions: ["READ"]
---

## Symptom
Two requests hitting the same logical cache key, close together in time, return different values — not because of a missing invalidation (the value was in fact updated) but because they happened to be served by different nodes in a replicated/clustered cache, and replication between those nodes hadn't caught up yet. The bug is often intermittent and hard to reproduce on demand because it depends on which node a given request happens to be routed to and the current replication lag, which is usually small but never zero.

## Likely causes
1. **The team assumed the cache cluster behaves like a single logical store** (strong consistency across nodes) when the actual technology's replication model is asynchronous/eventually consistent between nodes or shards, which is true of many distributed and managed caching services by default.
2. **Code relies on a "write then immediately read" pattern for correctness** (e.g., write a value, then read it back on the same request to confirm or use it) without pinning the read to the same node/connection that served the write, so the read can land on a replica that hasn't caught up.
3. **A read-your-writes assumption leaks into business logic** — e.g., using the cache as a short-term lock or coordination mechanism ("if this key exists, someone else already claimed this job") when the cache doesn't guarantee that a write is visible to all nodes before the check happens.
4. **Client-side load balancing/routing to cache nodes changes between the write and the subsequent read** (different requests in the same user flow hit different nodes due to connection pooling or a proxy layer), so consistency assumptions that might hold within one node's view don't hold across the flow.
5. **Failover or resharding events temporarily increase replication lag or even briefly serve from a stale replica promoted to primary**, making an otherwise-rare inconsistency window much more likely right after an infrastructure event.

## Diagnose
1. Check the specific cache technology's documented consistency model (not an assumption) — does it offer linearizable reads, read-your-writes, or only eventual consistency between replicas/nodes, and under what configuration (e.g., read preference, quorum settings)?
2. Reproduce by writing a value and then issuing rapid reads while deliberately targeting different nodes/replicas (if the client allows specifying this, or by hitting different cluster endpoints directly) to measure actual observed replication lag under normal and elevated load.
3. Search the codebase for any pattern that treats a cache write followed by an immediate read, or a cache-based existence check, as authoritative for a correctness-sensitive decision (locking, deduplication, idempotency) — these are the spots where a consistency-model mismatch causes real bugs rather than just cosmetic staleness.
4. Check monitoring/logs for replication lag metrics on the cache cluster itself around the time of reported incidents, and specifically around any recent failover, rebalance, or scaling event.
5. Confirm which read/write mode or consistency setting the client library is actually configured with (e.g., nearest-replica reads vs. primary-only reads) — a default optimized for latency often trades away consistency without that tradeoff being an explicit, reviewed decision.

## Fix
Match the code's assumptions to the cache's actual guarantees rather than the other way around: for anything correctness-sensitive (locking, idempotency checks, read-your-writes UX expectations), either route those specific operations to read from the primary/authoritative node rather than a replica, use a consistency mode the client library offers that's strong enough for the operation (even at a latency cost, applied narrowly), or move that specific piece of logic off the cache entirely and onto the source of truth, which does offer the needed guarantee. For UX-level read-your-writes expectations (a user should see their own update immediately), consider client-side patterns like returning the just-written value directly from the write response rather than re-reading it from the cache at all.

## Pitfalls
Don't try to "fix" this by adding an artificial delay/sleep before the follow-up read — it reduces the frequency of the race without eliminating it, adds latency to every request to mask a rare case, and will resurface under higher replication lag (e.g., during a partial outage or rebalance) exactly when it's most costly to debug. Also avoid switching everything to strong-consistency/primary-only reads globally as a blanket fix — that erases the latency and availability benefits the distributed cache was chosen for in the first place; apply the stronger guarantee only to the specific operations that actually need it.

## Verify
Under a test that introduces artificial replication lag (or targets a known-lagging replica directly, if the cache technology allows it), exercise the specific correctness-sensitive code path and confirm it now behaves correctly regardless of which node answers — e.g., a deduplication check no longer double-processes when the check and the original write land on different nodes.
