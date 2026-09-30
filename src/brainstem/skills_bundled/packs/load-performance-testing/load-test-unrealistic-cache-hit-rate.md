---
name: load-test-unrealistic-cache-hit-rate
description: A load test shows excellent performance because all virtual users repeatedly request the same small set of data, hitting a warm cache that real, more varied traffic would rarely hit.
triggers: ["load test cache hit rate unrealistic", "load test too fast because of caching", "same test data every virtual user", "load test does not reflect real traffic pattern"]
permissions: ["READ"]
---

## Symptom

A load test reports excellent latency and throughput, well beyond what
seems plausible given the system's known architecture (a database query
that should be relatively expensive appears near-instant under load), and
production performance under comparable real traffic doesn't match those
numbers at all.

## Likely causes

- **All virtual users request the same small, fixed set of test data**
  (the same product ID, the same user account) instead of a realistic
  spread across the actual keyspace, so nearly every request after the
  first hits a warm cache rather than exercising a cold-path lookup.
- **Test data was generated with very low cardinality** (a handful of
  unique values reused across thousands of simulated requests), which
  doesn't represent the actual diversity of real production data being
  queried.
- **A CDN or reverse-proxy cache in front of the system under test caches
  aggressively** for the test's narrow, repeated request pattern in a way
  that wouldn't happen for real traffic's more varied requests.
- **The load test scenario doesn't simulate cache invalidation events**
  (writes, TTL expiry) that would occur under real usage, so the cache
  stays artificially warm for the entire test duration.

## Diagnose

1. Check the load test script/scenario configuration for how test data
   (IDs, keys, query parameters) is selected per virtual user -- a fixed
   value or a very small pool is the direct signature of this issue.
2. Compare cache hit-rate metrics (from the cache layer, CDN, or
   application-level cache instrumentation) during the load test against
   typical production cache hit rates for the same functionality -- a
   load test hit rate far higher than production's is a strong signal.
3. Estimate the real production keyspace cardinality (how many distinct
   products/users/records get queried in a representative time window)
   and compare against the load test's actual data variety.
4. Re-run a smaller version of the load test with deliberately
   randomized, high-cardinality test data and compare the resulting
   latency/throughput against the original results.

## Fix

Generate load-test data with cardinality and access-pattern distribution
that matches real production traffic as closely as practical -- sampling
real (anonymized) production key distributions is often more accurate
than guessing a "reasonable" synthetic distribution. Include realistic
write/invalidation traffic in the load test scenario alongside reads, so
cache behavior under the test reflects the churn a real cache experiences
rather than staying artificially warm. If some cache warmth genuinely is
expected in production (a legitimately hot small set of popular items),
model that explicitly as a known proportion of traffic (e.g. 80% hits on
a realistic "hot" subset, 20% spread across a long tail) rather than
either 100% hot or 100% uniformly random.

## Pitfalls

Don't overcorrect into fully random, uniform access patterns if real
traffic actually does have a realistic hot/cold split (e.g. a small
number of popular products genuinely do get disproportionate traffic) --
an unrealistically pessimistic test (assuming zero cache benefit) is just
as misleading as an unrealistically optimistic one, in the opposite
direction, and can lead to over-provisioning based on a scenario that
will never occur.

## Verify

Re-run the load test with corrected, realistic data distribution and
confirm the measured cache hit rate now matches production's actual
observed hit rate within a reasonable margin. Confirm the resulting
latency/throughput numbers are now consistent with what's actually
observed in production under comparable real load, closing the gap that
originally prompted the investigation.
