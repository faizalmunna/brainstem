---
name: load-test-error-paths-never-exercised
description: A load test only exercises the happy path under load, missing that error-handling code (retries, fallbacks, validation failures) performs far worse under the same load and degrades the whole system when triggered.
triggers: ["error handling slow under load", "load test only tests happy path", "retries overwhelm system under load", "fallback logic not load tested"]
permissions: ["READ"]
---

## Symptom

The system performs well under load in testing, but a production
incident (invalid input from a client, a downstream dependency briefly
failing) that triggers the system's error-handling paths under similar or
even lower load causes far worse degradation than the load test ever
predicted -- sometimes cascading into a broader outage.

## Likely causes

- **The load test's synthetic requests are all valid, well-formed, and
  successful**, so the system's validation-failure, retry, and fallback
  code paths never execute at all during testing, leaving their
  performance characteristics completely unmeasured.
- **Error-handling code is inherently more expensive** than the happy
  path (a validation failure that constructs a detailed error response
  with additional lookups, a retry policy that makes multiple additional
  calls) but this cost was never included in any capacity planning
  because it was never exercised under load.
- **A retry policy without sufficient backoff/circuit-breaking amplifies
  load on an already-struggling downstream dependency** when a real
  failure occurs, turning a transient blip into a sustained overload --
  behavior a happy-path load test structurally cannot reveal.
- **Logging/alerting triggered by errors is itself expensive at volume**
  (synchronous logging, verbose error serialization) and only becomes a
  bottleneck when a real incident causes a spike in errors simultaneously
  with real load, a combination a pure happy-path test never creates.

## Diagnose

1. Review the load test's request generation logic and confirm what
   fraction (if any) of requests are designed to trigger validation
   failures, timeouts, or downstream error responses -- a 0% or
   near-0% error-path rate is the direct signature of this gap.
2. Deliberately inject failures into a downstream dependency (via
   `cy.intercept()`-style fault injection at the appropriate layer, a
   chaos-engineering tool, or a test double configured to fail a
   percentage of calls) while running load, and measure the system's
   behavior under that combined condition specifically.
3. Check retry/circuit-breaker configuration for whether it's actually
   tuned to prevent amplifying load on a struggling dependency, or
   whether it was configured without ever being tested under real
   concurrent load.
4. Check whether logging/error-handling code paths were included in any
   profiling done as part of capacity planning.

## Fix

Extend load test scenarios to deliberately include a realistic proportion
of error-triggering requests (invalid input, requests designed to hit
retry/fallback logic) alongside the happy path, and separately run a
combined load-plus-fault-injection test (load at a realistic level while
a downstream dependency is made to fail) to specifically measure the
system's behavior in the failure scenario that matters most for
resilience. Tune retry policies with backoff and circuit-breaking based
on what this combined test actually reveals about safe retry behavior
under load, rather than a policy configured only in isolation without
concurrent load.

## Pitfalls

Don't treat error-path load testing as a one-time addition -- as retry
policies, validation logic, and downstream dependencies change, the
error-path performance characteristics can regress independently of the
happy path, so include it as a standing part of load testing, not a
one-off audit. Also don't inject faults so aggressively (100% failure
rate) that the test only reveals behavior at an unrealistic extreme --
model realistic failure rates and durations based on what actual past
incidents looked like.

## Verify

Re-run the combined load-plus-fault-injection scenario after tuning retry/
circuit-breaker behavior and confirm the system degrades gracefully
(rejecting or shedding load predictably) rather than cascading into a
broader failure, and confirm the downstream dependency isn't further
overwhelmed by retry amplification during the simulated failure window.
