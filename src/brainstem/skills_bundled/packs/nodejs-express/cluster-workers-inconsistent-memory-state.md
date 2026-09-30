---
name: cluster-workers-inconsistent-memory-state
description: Diagnose an Express app run under Node cluster or multiple PM2 instances where in-memory caches, rate limits, or session data behave inconsistently across requests.
triggers: ["rate limit works locally but not in production", "in-memory cache inconsistent across requests", "session lost intermittently pm2 cluster", "different data depending on which server handled request", "cluster mode bug"]
permissions: ["READ"]
---

## Symptom
Behavior that depends on server-side in-memory state is inconsistent in
a way that correlates with *which request* is served, not with any
change in the underlying data -- a rate limiter that lets far more
requests through than configured, an in-memory cache that appears to
"forget" values it should have, WebSocket messages that only reach some
connected clients, or a user's session/login state flickering between
requests. It typically only appears in a deployed/production environment
running multiple processes (Node `cluster`, PM2 in cluster mode, multiple
container replicas) and not in a single-process local dev setup.

## Likely causes
1. **In-memory state (a `Map`, a plain object, a counter) is process-
   local**, and cluster mode runs N independent Node processes each with
   their own separate memory -- a rate limiter counting requests in a
   local `Map` counts only the requests *that specific worker* handled,
   not the true total, so the effective limit becomes (configured
   limit) x (worker count).
2. **Sessions stored in an in-memory session store**
   (`express-session`'s default `MemoryStore`) with a load balancer that
   doesn't use sticky sessions -- a user's session data lives only in the
   worker process that first created it, so any subsequent request routed
   to a different worker sees no session at all.
3. **A cache populated lazily on first access, per worker**, so each
   worker independently experiences a "cold" cache miss for the same key
   at different times, producing inconsistent latency and, if the
   underlying data changed between misses, inconsistent values across
   workers for what should be the same cached entry.
4. **A `setInterval`/cron-style background task defined at module scope**
   running independently and redundantly in every worker (e.g. a
   "send daily digest" job), producing duplicated side effects
   proportional to worker count instead of running once.

## Diagnose
- Confirm the deployment topology first: is this running under Node's
  `cluster` module, PM2 in `cluster` mode, or multiple container/VM
  replicas behind a load balancer? Any of these means multiple OS
  processes, and therefore multiple separate memory spaces, even though
  the code looks single-process when run locally.
- Log the worker/process id (`cluster.worker.id` under `cluster`, or
  `process.env.pm_id` under PM2, or the container hostname) alongside the
  in-memory state being debugged (current rate-limit count for a key,
  cache hit/miss) on every request -- if the same logical client's
  requests show different worker ids across consecutive requests, and the
  reported state differs by worker id, that directly confirms
  process-local state is the cause.
- For the rate-limiter case specifically: send a burst of requests
  exceeding the configured limit and count how many succeed; if the
  number that succeed is roughly (configured limit) times (number of
  worker processes), that ratio is close to diagnostic on its own.
- For the session case: check the load balancer/reverse proxy config for
  session affinity (sticky sessions) and check `express-session`'s
  configured store -- `MemoryStore`'s own startup log/warning explicitly
  states it's not for production/multi-process use if a version prints
  it.

## Fix
- Move shared state that must be consistent across all workers out of
  process memory and into a shared store: Redis for rate limiters,
  caches, and pub/sub-style coordination; a database or Redis-backed
  session store (`connect-redis` or equivalent) for sessions instead of
  `MemoryStore`.
- For rate limiting specifically, use a rate-limiting library/middleware
  backed by a shared store (Redis-backed `rate-limit-redis` with
  `express-rate-limit`, or equivalent) so the count is global across
  workers instead of per-process.
- For scheduled/interval background work that must run exactly once
  regardless of worker count, either designate a single worker to run it
  (e.g. `cluster.isPrimary` in the primary process, or check
  `process.env.NODE_APP_INSTANCE === '0'` under PM2) or move it to a
  dedicated single-instance job runner/queue outside the web-serving
  cluster entirely.
- If sticky sessions are the intended fix (rather than a shared store),
  configure the load balancer explicitly for session affinity -- but
  prefer a shared store where possible, since sticky sessions reintroduce
  the problem on worker restarts/redeploys and unbalance load across
  workers.

## Pitfalls
- Switching to a shared Redis-backed store fixes correctness but adds a
  network round-trip to what was previously an in-memory operation --
  re-check latency-sensitive paths (a rate-limit check on every request)
  under load after the change, since a slow or saturated Redis instance
  can now become the new bottleneck.
- Using sticky sessions as the fix instead of a shared store creates an
  uneven load distribution if some sessions are much more active than
  others, and breaks session continuity on worker crashes/redeploys --
  it's a narrower fix than it looks.
- "Fixing" the redundant-cron-job pattern by adding a random jitter/delay
  per worker reduces collision frequency but doesn't eliminate duplicate
  execution -- use an explicit single-owner check or an external
  scheduler, not a probabilistic one.

## Verify
Under the actual multi-worker/multi-replica deployment configuration
(not a single-process local run), repeat the burst-request test for
rate limiting and confirm the total allowed requests matches the
configured limit regardless of worker count, and confirm a session
created on one request is correctly readable on a subsequent request
regardless of which worker/replica handles it.
