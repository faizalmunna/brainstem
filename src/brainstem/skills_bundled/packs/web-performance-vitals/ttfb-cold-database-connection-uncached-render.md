---
name: ttfb-cold-database-connection-uncached-render
description: Diagnose slow TTFB on server-rendered pages caused by every request opening a fresh database connection and running uncached queries.
triggers: ["TTFB is slow", "server response time is high", "time to first byte", "SSR page slow to respond", "database connection slow on every request"]
permissions: ["READ"]
---

## Symptom
Lighthouse/PageSpeed flags high TTFB (>600-800ms) specifically for
server-rendered HTML responses, and the delay is on the server side (the
Network panel shows a long "Waiting (TTFB)" phase, not slow download or
DNS/connect time) -- often worse on the *first* request after a period of
inactivity and better on subsequent requests.

## Likely causes
1. **No connection pooling** -- the app opens a new database connection
   per request (or per process/worker restart) instead of reusing a warm
   pool, and connection setup (TCP handshake, auth, TLS) adds real latency
   on every single request.
2. **No query result caching** for data that doesn't change per-request
   (e.g. site-wide navigation data, product catalog data queried fresh on
   every page load instead of from an application cache/Redis).
3. **Serverless/cold-start environment** where the compute instance itself
   (not just the DB connection) spins up from zero on infrequent traffic,
   adding both runtime cold-start and a fresh connection on top.
4. **N+1 queries or an unindexed query in the server-rendering path**,
   where the absolute per-query time is fine but the SSR path makes many
   sequential round-trips before it can render anything.
5. **A synchronous, blocking external API call** (not the database at all)
   in the server-render path -- e.g. fetching pricing from a third-party
   service on every request with no cache.

## Diagnose
- In DevTools Network panel, check the "Timing" tab for the document
  request -- a large green "Waiting for server response" bar confirms
  server-side delay, ruling out client-side causes.
- Add server-side timing instrumentation (the `Server-Timing` response
  header, or APM traces from Datadog/New Relic/OpenTelemetry) that breaks
  down the request into DB-connect, query, render phases -- this
  distinguishes "connection setup slow" from "query itself slow" from
  "render/serialize slow."
- Check the database's active-connections metric during a slow request --
  if connections spike and reset frequently rather than staying steady,
  pooling isn't working.
- Compare TTFB for a request right after a period of idle traffic versus
  one in a burst of traffic -- a large gap points at cold starts (compute
  or connection) rather than steady-state query cost.

## Fix
The core pattern is to remove per-request setup cost from the hot path
entirely, either by keeping resources warm across requests or by not
needing them at all for content that doesn't change per-request.
Concretely: use a connection pool (PgBouncer, a driver-level pool, or your
platform's managed pooling for serverless DBs) sized appropriately for
concurrent request volume, so connections are reused instead of
established fresh; cache query results that are shared across users/
requests (page-level cache, fragment cache, or an in-memory/Redis cache
for expensive-but-rarely-changing lookups) with an invalidation strategy
tied to when the underlying data actually changes; for serverless, use
provisioned concurrency or a keep-warm strategy for latency-sensitive
routes, and choose a database access pattern designed for serverless cold
starts (HTTP-based DB proxies rather than raw TCP connections that can't
be reused across invocations); and batch/parallelize independent queries
in the render path instead of awaiting them sequentially.

## Pitfalls
- Oversizing the connection pool to "fix" this can exhaust the database's
  max-connections limit under real concurrent load, causing a different
  failure mode (connection refused errors) -- size the pool against the
  DB's actual limits and expected concurrency, not arbitrarily large.
- Caching query results without a correct invalidation trigger leads to
  stale data being served long after the underlying data changed --
  tie cache invalidation to the actual write path, not just a TTL, for
  anything where staleness is user-visible and costly.
- Fixing the database connection cost but missing a blocking third-party
  API call (cause 5) in the same render path leaves TTFB just as bad --
  the Server-Timing breakdown should confirm which phase actually
  improved.

## Verify
Re-check the `Server-Timing` header or APM trace breakdown to confirm the
specific phase you targeted (connection setup, query time) actually
shrank, and re-measure TTFB via WebPageTest or Lighthouse across both a
cold (post-idle) request and a warm one to confirm both improved, not just
the warm-path average.
