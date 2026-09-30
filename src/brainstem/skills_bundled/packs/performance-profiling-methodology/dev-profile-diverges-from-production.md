---
name: dev-profile-diverges-from-production
description: A profiler run locally or in staging points to a completely different bottleneck than the one actually causing slowness in production.
triggers: ["profiler shows different results in staging vs prod", "local profile doesn't match production slowness", "optimized the wrong thing based on the dev profile", "profiling environment doesn't reflect production"]
permissions: ["READ"]
---

## Symptom

A profile taken on a laptop, in CI, or in a staging environment clearly
identifies one function or query as the hot path. The team optimizes it,
ships it, and production behavior barely changes -- because production's
actual bottleneck was something else entirely, invisible in the
lower-fidelity environment where the profile was taken.

## Likely causes

- **Data volume mismatch.** Staging/dev databases are often orders of
  magnitude smaller, so operations that are O(n) or worse over a
  collection (a full table scan, an in-memory sort, a nested loop join)
  look cheap locally and become the dominant cost only at production
  scale.
- **Data shape/skew mismatch.** Synthetic or sampled test data is often
  uniform, while production data has skew (a few huge tenants, hot
  keys, long-tail cardinality) that triggers pathological behavior --
  cache misses, index scans instead of seeks, hash collisions -- only
  under the real distribution.
- **Concurrency mismatch.** A single-user local profile can't reveal
  lock contention, connection pool exhaustion, or queueing delay that
  only appears under concurrent production load; the profiled code path
  may be fast in isolation and slow only when many requests compete for
  the same resource.
- **Infrastructure mismatch.** Local runs often hit warm in-memory
  caches, localhost network (near-zero latency), and no cross-AZ or
  cross-region hops, all of which hide network- and cache-miss-driven
  costs that dominate in the real deployment topology.
- **Different code path entirely.** Feature flags, environment-specific
  branches, or config defaults (e.g., debug logging, disabled caching)
  can mean dev and prod are not even executing the same code shape.

## Diagnose

1. Compare data volume and cardinality between the environment profiled
   and production for the tables/collections/queues involved (row
   counts, distinct key counts, payload sizes) -- an order-of-magnitude
   gap is disqualifying for that profile's conclusions.
2. Check whether the profiled environment's config matches production
   for the things that change hot paths: cache enabled/disabled, log
   level, connection pool size, feature flags, and whether it's running
   the same build (not a debug build with assertions/instrumentation on).
3. Prefer profiling production directly with a low-overhead, safe
   mechanism: continuous/always-on profilers (e.g., sampling profilers
   designed for production use), or capture flame graphs from a
   canary/shadow instance receiving real traffic.
4. If production profiling isn't available, at minimum replay a
   realistic production traffic sample (captured requests, or a
   production data snapshot with PII scrubbed) against the staging
   environment before trusting its profile.
5. Cross-check the profile's claimed hot path against production APM/
   trace data for the same endpoint -- if they disagree, trust production.

## Fix

Treat any profile taken outside production as a hypothesis, not a
conclusion, until corroborated by production signal (APM traces, real
request sampling, or a production-safe profiler). Where feasible, invest
in always-on low-overhead production profiling (continuous profiling
tools using statistical sampling with sub-1% overhead) so the "profile
in dev" step is unnecessary for anything but initial hypothesis
generation. When production profiling truly isn't possible, make
staging data-representative: seed it from a scrubbed production snapshot
or a generator that reproduces realistic volume and skew, not hand-
written fixtures sized for convenience.

## Pitfalls

Don't assume a bigger staging dataset alone fixes this -- skew and
concurrency patterns matter as much as row count, and a large-but-
uniform synthetic dataset can still miss the hot-key or lock-contention
behavior that only shows up with real traffic shape. Also don't treat
"we don't have a profiler that's safe for production" as a permanent
excuse; most modern continuous profilers are built specifically for
low-overhead always-on production use, and the setup cost is usually
smaller than the recurring cost of chasing wrong bottlenecks.

## Verify

After identifying a candidate fix from a production-corroborated
profile, confirm the specific production metric (trace span duration,
endpoint p95, resource utilization graph) that motivated the
investigation actually moves post-deploy, and re-profile production
afterward to confirm the previously dominant frame/span has shrunk as
predicted.
