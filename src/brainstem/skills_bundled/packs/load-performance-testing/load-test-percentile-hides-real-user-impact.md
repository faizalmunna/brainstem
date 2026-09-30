---
name: load-test-percentile-hides-real-user-impact
description: A load test's summary latency numbers look acceptable while a smaller but real subset of users experiences timeouts, because only averages or a single percentile were reported.
triggers: ["load test average looks fine but users complain", "p99 latency ignored", "load test summary misleading", "average latency hides outliers"]
permissions: ["READ"]
---

## Symptom

A load test's summary report shows an acceptable average or median
response time, and the test is signed off as passing, but real users
under similar load report timeouts or very slow responses -- a real
performance problem that the summary metric never surfaced.

## Likely causes

- **Only mean/median latency was reported**, which can look healthy even
  when a meaningful percentage of requests take dramatically longer --
  averages are pulled toward the bulk of fast requests and don't reflect
  the tail.
- **A high percentile (p95/p99) was measured but not treated as a pass/
  fail criterion**, so it was visible in the report but not actually
  acted on when it exceeded an acceptable threshold.
- **The test duration was too short to capture tail latency events that
  only occur periodically** (a GC pause, a cache eviction, a connection
  pool exhaustion event), so a short run's percentile numbers understate
  what a longer, more realistic duration would reveal.
- **Real user traffic includes request types/payload sizes with
  different latency profiles** than the load test's uniform request mix,
  so the test's percentiles don't represent the full range of real-world
  request costs.

## Diagnose

1. Re-examine the load test's raw results (not just the summary) for the
   full latency distribution -- specifically p95, p99, and max, not just
   mean/median.
2. Check whether a percentile-based threshold was part of the test's
   pass/fail criteria at all, or whether "passing" was defined only by
   throughput and average latency.
3. Compare the load test's duration against how long a similar real
   production incident window typically needs to manifest (some tail
   latency causes, like GC pauses or connection pool exhaustion under
   sustained load, only appear after minutes, not seconds).
4. Compare the load test's request mix (endpoint types, payload sizes)
   against real production traffic logs to identify whether a
   higher-latency request type is underrepresented in the test.

## Fix

Make percentile-based latency (p95/p99, and ideally p99.9 for
high-traffic systems) an explicit, monitored pass/fail criterion for load
tests, not just a number in a report nobody checks. Run load tests for a
duration long enough to surface periodic tail-latency causes, not just a
short burst that only captures steady-state best-case behavior. Build the
test's request mix from real production traffic patterns (sampled logs)
rather than a uniform synthetic mix, so the tail latency measured
actually reflects the tail latency real users would experience.

## Pitfalls

Don't chase p99.9 or p100 (max) as a hard pass/fail gate without
understanding that a small number of genuinely anomalous outliers
(a one-off network blip unrelated to the system under test) can make
that specific percentile misleadingly noisy -- pick a percentile
threshold that's both meaningful to user experience and statistically
stable enough to reason about run to run. Also don't fix a p99 problem
by simply extending timeouts everywhere -- that hides the slow-request
symptom from monitoring without actually improving the experience for
the affected users.

## Verify

Re-run the load test with p95/p99 explicitly gated as pass/fail criteria
and confirm they're now tracked and enforced in whatever CI/reporting
process consumes load test results. Cross-reference the tail latency
numbers against actual production APM data for the same endpoints under
comparable real load, to confirm the load test's tail behavior is now
representative of what's actually observed.
