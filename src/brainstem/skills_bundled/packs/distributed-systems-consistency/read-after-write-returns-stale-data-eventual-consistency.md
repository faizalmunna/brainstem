---
name: read-after-write-returns-stale-data-eventual-consistency
description: A client reads back its own recent write and occasionally gets the old value because the backing store only guarantees eventual consistency.
triggers: ["read after write returns old value", "just wrote data but read shows stale value", "eventual consistency causing stale reads", "user doesn't see their own update immediately"]
permissions: ["READ"]
---

## Symptom

An application writes a value, then immediately reads it back (often
in the very next request, or a redirect after a form submission, or a
UI that refetches after a mutation), and occasionally -- not always,
which is the telltale sign -- gets the previous value instead of the
one just written. It's intermittent, harder to reproduce under low
load, and gets worse under high write volume or when reads are routed
to a different replica/region than the write.

## Likely causes

- **Reads are served from a replica that hasn't yet received the
  write**, common with read replicas, multi-region databases, or
  managed services (DynamoDB default reads, Cosmos DB session-
  inconsistent configurations, MySQL/Postgres read replicas) that are
  eventually consistent by design and default -- the application code
  was written assuming strong consistency that the storage layer never
  actually promised.
  contract that the storage layer never actually promised.
- **A cache sits between the write path and the read path and isn't
  invalidated synchronously with the write** -- the write succeeds
  against the source of truth, but a cache (CDN, application cache,
  read-through cache) still serves the pre-write value until its TTL
  expires or an async invalidation event is processed.
- **The write and the subsequent read are load-balanced to different
  backend instances or database connections without session
  affinity**, and there's no mechanism (sticky routing, read-your-
  writes token, causal token) ensuring the read observes at least the
  write that just happened from the same client.
- **Search indexes or materialized views are updated asynchronously
  from the primary write path** (a common pattern for Elasticsearch,
  denormalized read models, CQRS projections), so a UI that reads from
  the index/projection immediately after writing to the primary store
  sees stale results until the async indexing job catches up.

## Diagnose

1. Reproduce with explicit timing: write, then read immediately, then
   read again after increasing delays (10ms, 100ms, 1s, 5s) and record
   at what delay the correct value reliably appears -- this measures
   the actual propagation lag rather than guessing.
2. Check which specific read path served the stale response: log or
   trace which replica/region/cache layer handled the read versus
   which node handled the write, using request tracing or
   per-replica connection logging.
3. For managed databases, check the documented consistency model and
   the actual client configuration (e.g. DynamoDB `ConsistentRead`
   flag, Cosmos DB consistency level, MongoDB read preference/read
   concern) against what the code assumes -- most of these default to
   the weaker, eventually-consistent option unless explicitly
   overridden.
4. If a cache is involved, check the cache invalidation path
   specifically: is it synchronous (invalidate-on-write, before the
   write is acknowledged to the client) or asynchronous (TTL expiry,
   event-driven invalidation with its own lag)?
5. Check load balancer / connection pool configuration for session
   affinity or read-your-writes routing hints between the write
   request and the subsequent read request from the same client.

## Fix

Decide, per use case, whether strong consistency is actually required
for that read -- many reads genuinely tolerate eventual consistency
(a follower count, a recommendation feed) and forcing strong reads
everywhere sacrifices the latency/availability benefits that eventual
consistency was adopted for in the first place. For reads that
specifically need read-your-writes behavior, use the mechanism the
store provides for it: strongly-consistent read flags on the specific
query, session-consistency tokens or causal tokens that pin
subsequent reads to at least the writer's version, or routing the
immediate post-write read back to the same node/replica that accepted
the write. For cache-based staleness, make the write path invalidate
(or update) the cache synchronously as part of the write transaction,
or have the client optimistically update its local view with the
known-good value instead of re-fetching. For async projections/search
indexes, either have the write-confirmation UI show the value it just
wrote directly (not by re-querying the projection) or expose the
projection's lag explicitly so callers can decide whether to wait.

## Pitfalls

Don't reach for "just always read from the primary" as a blanket fix
-- routing every read to the primary/leader defeats the purpose of
read replicas and can overload the primary under load, trading a rare
staleness bug for a capacity problem. Also don't paper over the
symptom by adding an arbitrary sleep between write and read; it
doesn't guarantee consistency (lag is variable and can exceed the
sleep under load) and just adds latency to every request for a
problem that needs a correctness mechanism, not a timing guess.

## Verify

Under realistic write load (not idle load, where lag is minimal),
run a scripted write-then-read loop against the fixed code path and
confirm zero stale reads across many iterations, including during a
synthetic load spike on the replica/cache layer. For the specific
consistency mechanism used (session token, strong-read flag, sticky
routing), confirm via tracing that the read request actually carries
and honors that mechanism rather than silently falling back to the
default eventually-consistent path.
