---
name: load-test-ramp-up-too-aggressive
description: A load test's overly steep ramp-up causes the system under test to reject connections or error out before reaching a steady state that would reveal its actual sustainable throughput.
triggers: ["load test errors during ramp up", "system rejects connections at start of load test", "load test ramp too steep", "load test never reaches steady state"]
permissions: ["READ"]
---

## Symptom

A load test reports a high error rate and poor latency almost
immediately after starting, with the errors concentrated in the first
seconds/minutes of the test, even though the target load level was
expected to be within the system's real capacity -- the run gets marked
as a failure, but the failure looks more like a burst shock than a
sustained capacity problem.

## Likely causes

- **The ramp-up profile increases load far faster than the system's
  autoscaling, connection-pool warm-up, or JIT/cache warm-up can keep
  pace with**, causing transient rejections that wouldn't occur if the
  same eventual load were reached more gradually.
- **A connection pool or thread pool sized for steady-state load takes
  time to actually grow to that size**, and a steep ramp overwhelms it
  before it finishes scaling up, producing errors that are an artifact of
  ramp speed rather than the system's true sustained capacity.
- **Autoscaling infrastructure (adding server instances) has an inherent
  lag** (image boot time, health-check grace periods) that a fast ramp
  doesn't give enough time to react to, so the system is measured at a
  smaller effective capacity than its scaled-out steady state would
  provide.
- **Downstream dependencies (a database, a cache) have their own
  connection-pool warm-up behavior** that a steep ramp exercises before
  they're ready, producing errors attributable to the dependency's warm-up
  rather than the system under test's actual limits.

## Diagnose

1. Look at the time series of error rate/latency across the test
   duration, not just the aggregate -- errors concentrated in the first
   portion of the run, improving as the test continues at the same or
   higher load, point at a ramp-up artifact rather than a true capacity
   ceiling.
2. Compare the configured ramp-up duration/slope against known
   warm-up characteristics of the system's own components (autoscaler
   reaction time, connection pool growth behavior, JIT warm-up for
   JVM-based services).
3. Re-run the same target load with a substantially longer, gentler
   ramp-up and compare error rates -- if errors disappear or drop
   sharply, ramp speed was the actual issue, not sustainable capacity.
4. Check autoscaling/infrastructure logs during the original run for
   scale-up events that were still in progress when peak load hit.

## Fix

Design the ramp-up profile to increase load at a rate the system's own
warm-up mechanisms (autoscaling, connection pools, caches) can reasonably
keep pace with, based on their known characteristics, rather than an
arbitrary fast ramp chosen just to reach the target quickly. Separate the
test's *goal* (measure sustained capacity at a target load) from a
*different, legitimate* test (measure behavior under a sudden traffic
spike/shock) -- these need different ramp profiles and should be treated
and reported as distinct test types, not conflated into one run's results.

## Pitfalls

Don't simply ignore or filter out ramp-up-period errors from the report
without understanding whether they're truly ramp artifacts or an early
warning of a real issue -- confirm via the re-run-with-gentler-ramp
comparison rather than assuming. Also, if sudden traffic spikes are a
real production scenario (a marketing event, a viral moment), don't skip
testing that shock scenario just because it's not the same as a steady-
state capacity test -- run both, explicitly labeled as testing different
things.

## Verify

Re-run the load test with an adjusted ramp profile appropriate to the
system's known warm-up behavior and confirm the error rate during ramp-up
drops to a level consistent with the eventual steady-state error rate.
Separately and explicitly, if a shock-load scenario matters for this
system, run and report that as its own distinct test with its own
criteria, rather than treating a fixed capacity number as the only
relevant load-testing outcome.
