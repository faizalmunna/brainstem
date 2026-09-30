---
name: single-request-testing-hides-contention
description: A single request performs well in manual testing but latency degrades sharply once multiple users hit the system concurrently.
triggers: ["works fine when I test it alone but slow under load", "latency fine in isolation but bad in production traffic", "connection pool exhausted under concurrent users", "lock contention only shows up with multiple users"]
permissions: ["READ"]
---

## Symptom

Manually testing an endpoint or workflow one request at a time shows
fast, consistent latency. Once real (or load-tested) concurrent traffic
hits the same system, latency degrades sharply and non-linearly --
worse than what the per-request cost would predict -- and the
degradation wasn't visible in any single-request test, no matter how
many times it was repeated sequentially.

## Likely causes

- **Connection pool exhaustion.** A database, HTTP client, or other
  resource pool sized for low concurrency works perfectly with one
  in-flight request; under concurrent load, requests queue for a pool
  slot, and that queueing time is invisible to a test that never has
  more than one request in flight.
- **Lock contention.** Code with a shared mutex, a row-level database
  lock, or an in-memory cache lock shows no contention at all with a
  single caller; under concurrency, serialization on the lock becomes
  the dominant cost, and the effect is worse than linear as waiters
  queue behind each other.
- **Shared resource saturation** (CPU cores, thread pool size, a
  downstream service's own rate limits) that only becomes the binding
  constraint once total concurrent demand exceeds capacity -- a single
  request never approaches that ceiling.
- **Head-of-line blocking in a single-threaded or limited-worker
  component** (an event loop, a single-threaded cache client, a
  serialized queue consumer) where one slow request delays all others
  queued behind it, an effect that by definition requires more than one
  concurrent request to exist.

## Diagnose

1. Run a load test that ramps concurrency (not just request rate) --
   e.g., fix request rate but increase the number of concurrent virtual
   users/connections -- and plot latency against concurrency level; a
   sharp inflection point (latency staying flat then rising steeply past
   some concurrency threshold) is the signature of a saturating shared
   resource.
2. During the load test, monitor pool-specific metrics directly: active
   vs. idle connections in the DB/HTTP client pool, queue depth/wait
   time for a pool checkout, thread pool queue length -- most pool
   implementations expose these; a growing wait-for-checkout time
   correlating with the latency rise confirms pool exhaustion.
3. Check for lock wait metrics or use a profiler with lock-contention
   visibility (many runtimes/APM tools support this) during the same
   concurrent load test, looking for time attributed to acquiring a
   specific lock rather than doing work.
4. Compare per-request resource usage (CPU, memory, one DB connection)
   at low concurrency against the theoretical capacity of shared
   resources (pool size, core count, downstream rate limit) to predict
   the concurrency level where saturation should occur, and check
   whether the observed inflection point matches.

## Fix

Size shared resources (connection pools, thread pools, worker counts)
based on expected concurrent load and the actual hold time of each
resource use, not guessed defaults -- pool size should be a deliberate
capacity decision, verified under load, not a framework default left
untouched. For lock contention, narrow the critical section (hold the
lock for the minimum necessary work), consider sharding the lock or
resource (e.g., per-key locks instead of one global lock), or move to a
lock-free/optimistic approach where contention is proven to be the
bottleneck. Always validate the fix under the same concurrency profile
that revealed the problem, not just at low concurrency again.

## Pitfalls

Don't respond to contention symptoms by blindly increasing pool or
thread counts without checking the downstream resource's own capacity
(e.g., increasing an app's DB connection pool size when the database
itself is the one running out of capacity just moves the queueing
further downstream, or overwhelms the database instead). Also don't
trust a load test that only increases request *rate* while keeping
concurrency low (e.g., via think-time/pacing) -- rate and concurrency are
different dimensions, and contention effects are driven by concurrency
specifically.

## Verify

Re-run the same ramped-concurrency load test after the fix and confirm
the latency-vs-concurrency curve no longer shows the sharp inflection at
the previous threshold, and that pool/lock wait-time metrics stay near
zero up to the target concurrency level the system needs to support in
production.
