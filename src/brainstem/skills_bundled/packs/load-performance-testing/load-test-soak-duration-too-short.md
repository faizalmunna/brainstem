---
name: load-test-soak-duration-too-short
description: A short load test passes cleanly but the system degrades or crashes after hours of sustained load in production due to a slow resource leak that never had time to manifest during testing.
triggers: ["memory leak only appears after hours", "soak test needed", "system degrades over time not immediately", "load test too short to catch leak"]
permissions: ["READ"]
---

## Symptom

The system passes load testing at the target throughput with good
latency for the duration of the test (typically minutes), but in
production, performance degrades gradually over hours (increasing
latency, rising memory usage, eventual crash/restart) under sustained
real traffic at a similar or even lower load level.

## Likely causes

- **A slow memory leak** (an unclosed resource, a growing cache with no
  eviction, an accumulating event listener) that only becomes measurable
  after many hours of sustained operation, invisible in a short test run.
- **Connection pool or file descriptor exhaustion from a slow leak** in
  resource cleanup that only crosses a critical threshold after
  processing a very large cumulative number of requests, not detectable
  from a short burst.
- **A scheduled/periodic background task** (a cache cleanup job, a log
  rotation) that runs infrequently (hourly, daily) and briefly degrades
  performance in a way a short load test's window never overlaps with.
- **Log file or temp file growth on disk** eventually filling available
  disk space or slowing down I/O, an effect that compounds only over a
  long enough duration.

## Diagnose

1. Run a soak test -- sustained load at a realistic (not necessarily
   peak) level for several hours to overnight -- while monitoring memory,
   file descriptor count, disk usage, and latency trends over the entire
   duration, not just a snapshot.
2. Look for a monotonically increasing trend (not just noise) in any
   resource metric across the soak test's duration -- a genuine leak
   shows a clear upward trend rather than fluctuating around a stable
   baseline.
3. Correlate any observed periodic latency spikes during the soak test
   against the system's own scheduled/cron job configuration to rule out
   (or confirm) a periodic background task as the cause.
4. If a leak is confirmed, use memory profiling tools appropriate to the
   runtime (heap dumps and diffing for JVM/Node, `tracemalloc` for
   Python, etc.) taken at the start and after several hours to identify
   what's actually accumulating.

## Fix

Fix the specific identified leak (close the actual unclosed resource, add
eviction/bounds to an unbounded cache, remove an accumulating listener)
based on what the profiling step actually revealed -- there's no generic
fix here, it depends entirely on what's leaking. Separately, make soak
testing (multi-hour, sustained, realistic load) a standing part of the
release/testing process for any system expected to run continuously,
distinct from short burst-style load tests that are better suited for
measuring peak throughput and immediate response to load changes.

## Pitfalls

Don't treat a soak test's success as permanent once passed -- a leak can
be reintroduced by a later, seemingly unrelated code change, so soak
testing needs to be a recurring practice (ideally automated, run
regularly against each release candidate) rather than a one-time
validation. Also don't assume restarting affected production instances
periodically (a workaround some teams adopt) is an acceptable permanent
fix -- it masks the leak's user-facing impact without addressing the
underlying resource management bug, and the required restart interval
tends to shrink over time as the codebase grows.

## Verify

After the fix, re-run the same soak test duration and confirm the
previously-leaking resource metric now stays flat (within normal
fluctuation) across the full multi-hour window rather than trending
upward. If feasible, run an even longer soak (extending past the original
test's duration) to build additional confidence the leak is fully
resolved rather than just slowed down.
