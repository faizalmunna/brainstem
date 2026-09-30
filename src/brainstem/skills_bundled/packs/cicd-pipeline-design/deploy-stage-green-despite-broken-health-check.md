---
name: deploy-stage-green-despite-broken-health-check
description: A pipeline's deploy stage reports success and the health check passes even though the newly deployed version is actually broken in production.
triggers: ["deploy passed but service is down", "health check green but app broken", "pipeline succeeded but prod is broken", "readiness probe passing but app not working", "deploy gate didn't catch the regression"]
permissions: ["READ"]
---

## Symptom
The deploy stage in the pipeline finishes green, the configured health
check reports healthy, and yet the newly deployed version is actually
broken for real users -- returning errors on the actual business
endpoints, unable to reach a dependency, or serving stale/wrong data --
within minutes of the "successful" deploy.

## Likely causes
1. **The health check only verifies the process is up, not that it
   works** -- a `/healthz` endpoint that returns 200 as long as the HTTP
   server is listening, with no check of database connectivity, downstream
   dependency reachability, or any actual business logic path.
2. **The health check runs too early relative to real traffic** -- it's
   checked once immediately after the process starts (or against a
   synthetic empty request) before caches warm, connection pools
   establish, or background initialization completes, so it passes during
   a window that doesn't represent steady-state behavior.
3. **The check targets the wrong layer** -- a load balancer or
   orchestrator-level check (e.g. Kubernetes readiness probe hitting TCP
   connect only) is treated as sufficient proof of a successful deploy,
   when the pipeline never independently validates the application-level
   contract (a real endpoint returning the expected shape/status).
4. **The check has a threshold or retry policy that masks failure** -- it
   allows enough consecutive failures or such a generous timeout before
   marking unhealthy that the pipeline's deploy stage has already reported
   success and moved on before the probe would ever fail.
5. **The health check was copy-pasted from another service** and checks
   a dependency or endpoint that happens to exist on both but isn't the
   one that actually broke -- so it's testing something real, just not
   the thing that regressed.

## Diagnose
- Read the exact health check implementation (endpoint handler code, not
  just its route name) and list every dependency/code path it actually
  exercises versus what the real regression touched -- if the incident
  was, say, a broken downstream payment API call and the health check
  never calls that dependency, that's the gap, concretely identified.
- Check the gate's timeout, interval, and failure-threshold configuration
  against how long the real regression took to manifest -- compute
  whether the gate even had enough observation time to catch it before
  the pipeline moved on.
- Diff the health check config between this service and a known-good
  sibling service to catch a copy-paste mismatch.
- Look at what actually gated the pipeline's "success" state: is it the
  orchestrator's readiness probe (infra-level), a separate synthetic
  smoke test (pipeline-level), or nothing beyond "the deploy command
  didn't error"?

## Fix
Separate two distinct concerns that get conflated into one shallow check:
orchestrator-level liveness/readiness (is the process able to receive
traffic at all) versus pipeline-level deploy validation (did this specific
release actually work). Keep the readiness probe simple and fast for the
orchestrator's own traffic-routing decisions, but add a dedicated
post-deploy verification stage in the pipeline that exercises real
business-critical paths -- hit actual API endpoints with representative
requests, verify response shape and status, check a canary of real (or
realistic synthetic) traffic's error rate over a window long enough to
catch delayed failures -- and make the pipeline's success status
conditional on that verification stage, not on the orchestrator's probe
alone.

## Pitfalls
- Making the post-deploy check exhaustive to the point that it becomes
  slow and flaky itself (testing every endpoint, every edge case) --
  this trains people to treat its failures as noise. Scope it to the
  handful of paths that represent genuine "is this deploy fundamentally
  working" signals, and use broader test suites earlier in the pipeline
  instead.
- Adding depth to the health check but leaving its failure
  non-blocking (logged but not gating), which reproduces the exact
  original symptom in a new location -- always confirm the check's
  result actually stops or rolls back the pipeline, not just that it's
  being computed.

## Verify
Reproduce the original regression's root cause in a staging deploy of
the exact same pipeline (mock the broken dependency response) and confirm
the pipeline's deploy stage now fails/blocks specifically because of the
new post-deploy verification step, with the failure reason in the
pipeline log pointing at the real broken path rather than a generic
timeout.
