---
name: load-test-metrics-not-correlated-with-bottleneck
description: A load test identifies that the system degrades under load but never identifies which specific resource (CPU, database, network) actually caused it, because client-side results were never correlated with server-side metrics.
triggers: ["load test shows degradation but not why", "don't know what caused load test failure", "correlate load test with server metrics", "load test result without root cause"]
permissions: ["READ"]
---

## Symptom

A load test clearly shows the system degrading past a certain load level
(latency rising, error rate climbing), but the investigation stalls
there -- nobody can say definitively whether the bottleneck was CPU,
database connections, memory, network, or something else, because the
load test's client-side results were never lined up against server-side
metrics from the same time window.

## Likely causes

- **The load-testing tool's output and the application's/infrastructure's
  monitoring system are two separate, disconnected views**, with no
  shared timeline or dashboard making it easy to overlay "requests/sec
  and latency from the load test" against "CPU/memory/DB connections from
  APM" for the exact same time period.
  during the load test.
- **Server-side monitoring wasn't running with sufficient granularity**
  during the test (metrics scraped every few minutes instead of every
  few seconds), too coarse to correlate with a load ramp that changes
  meaningfully within that window.
- **The load test and the monitoring dashboards use different, unsynced
  clocks or time zones**, making manual correlation error-prone even when
  both data sets technically exist.
- **Nobody explicitly instrumented the specific suspected resources**
  (connection pool utilization, queue depth, GC pause time) beyond
  generic CPU/memory, so even a perfectly time-aligned correlation
  wouldn't reveal a bottleneck in an uninstrumented resource.

## Diagnose

1. Confirm what server-side metrics were actually being collected during
   the load test run, at what granularity, and whether they cover the
   specific resources most likely to bottleneck for this system (DB
   connection pool, cache, downstream service latency, GC activity, not
   just CPU/memory).
2. Re-run the load test (or a smaller repeat) with both the load-testing
   tool's dashboard and the server-side APM/monitoring dashboard open
   side by side, using synchronized timestamps, and manually mark where
   degradation begins on both.
3. If available, use a load-testing tool/platform that supports
   annotating APM traces with load-test markers, or export both data sets
   to a common analysis tool for proper time-series correlation.
4. For the specific point where degradation begins, check each candidate
   resource's metric at that exact timestamp to see which one crossed a
   meaningful threshold (saturation, queueing) right before latency/error
   rate moved.

## Fix

Set up load tests to run with server-side monitoring at matching or finer
granularity than the load ramp's own resolution, covering the specific
resources most plausible for this system's architecture (not just
generic CPU/memory). Use a shared time reference (synchronized clocks,
ideally a single dashboard or tool that overlays both data sets) so
correlation doesn't depend on manual timestamp matching across separate
systems. Treat "what specifically bottlenecked" as a required output of
every load test, not an optional follow-up investigation -- build the
correlation step into the standard load-testing process rather than only
doing it reactively when a test fails and someone needs an answer.

## Pitfalls

Don't assume the first resource that looks elevated at the point of
degradation is necessarily the actual cause -- a resource can spike as a
downstream effect of a different, less obvious bottleneck (e.g. thread
pool exhaustion from waiting on a slow database, not the thread pool
itself being the root cause). Trace the causal chain rather than stopping
at the first correlated metric.

## Verify

After identifying and fixing the actual bottleneck, re-run the same load
test and confirm the system now sustains the previously-degrading load
level with the previously-implicated resource's metric staying within a
healthy range, while overall latency/error rate improve correspondingly.
