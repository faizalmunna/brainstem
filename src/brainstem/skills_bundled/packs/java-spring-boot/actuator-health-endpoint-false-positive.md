---
name: actuator-health-endpoint-false-positive
description: The Spring Boot Actuator health endpoint reports the application as UP while a critical downstream dependency it relies on is actually down or degraded.
triggers: ["health check says up but app is broken", "actuator health false positive", "load balancer keeps routing to a broken instance", "health endpoint not catching real outage"]
permissions: ["READ"]
---

## Symptom

A load balancer, Kubernetes liveness/readiness probe, or monitoring tool
keeps treating an instance as healthy (`/actuator/health` returns `UP`)
while the application is actually failing real requests, because a
dependency it needs (database, downstream service, message broker) is
unreachable or degraded.

## Likely causes

- **No health indicator is registered for the failing dependency at
  all** -- Spring Boot auto-configures health indicators for some
  common dependencies out of the box, but a custom downstream service
  call, a specific cache, or a non-auto-detected client library has no
  indicator unless one is explicitly written.
- **A health indicator exists but only checks that a connection *can be
  established*, not that the dependency actually responds correctly** --
  e.g. a database indicator that opens a TCP connection but doesn't run
  a real query, missing a case where the connection succeeds but queries
  hang or error.
- **The liveness and readiness probes are conflated into one check** --
  a Kubernetes liveness probe restarting the pod is the wrong response to
  a downstream dependency being down (restarting won't fix an external
  outage), while a readiness probe should be failing to stop new traffic
  -- if both point at the same undifferentiated health group, the wrong
  remediation happens.
- **A health indicator's timeout is longer than the probe's own timeout**,
  so the probe treats a slow-but-technically-answering check as a timeout
  failure (or vice versa, treats a hung check as still "in progress" and
  keeps reporting stale status).
- **Health status caching** (Spring Boot can cache health results briefly)
  masking a very recent state change from a probe that polls more
  frequently than the cache TTL.

## Diagnose

1. Call `/actuator/health` directly (with `management.endpoint.health.
   show-details=always` in a non-prod-safe way, or check logs/metrics)
   during a known dependency outage and inspect exactly which components
   are checked and what each one's individual status was.
2. Check whether a health indicator exists for the specific dependency
   that failed -- list registered `HealthIndicator`/`HealthContributor`
   beans and cross-reference against every real external dependency the
   app has.
3. For an existing indicator that should have caught the failure, check
   what it actually does (connection-only vs. a real functional check)
   and whether its timeout is shorter than the probe's timeout.
4. Check the actual probe configuration (liveness vs. readiness, their
   respective Spring Boot health groups via `management.endpoint.health.
   group.*`) to confirm they're pointed at intentionally different
   checks, not the same undifferentiated status.

## Fix

Write a custom `HealthIndicator` for every real external dependency the
application depends on for correct operation, and make each one perform
a minimal *functional* check (a lightweight real query, not just a
connection open) with a timeout shorter than the probe's own timeout so
a hang reports unhealthy rather than appearing to hang the probe itself.
Split health into readiness (should this instance receive traffic right
now -- fail on downstream dependency issues) and liveness (should this
process be restarted -- fail only on conditions a restart would actually
fix, like a deadlocked internal state) using Spring Boot's health groups,
and point the orchestrator's two separate probes at the two separate
groups rather than one shared endpoint.

## Pitfalls

Don't make every downstream dependency failure trigger a liveness-probe
restart -- restarting the instance does nothing for an external outage
and can cause a restart storm across all instances simultaneously
(potentially worse than the original problem, since it removes all
capacity briefly). Also don't add a functional check so expensive
(a full transaction, a heavy query) that the health check itself becomes
a meaningful load source when probed frequently across many instances --
keep functional checks minimal and cheap.

## Verify

Simulate the original failure condition (block/stop the actual
dependency in a non-prod environment) and confirm `/actuator/health`
(and specifically the readiness group) now reports the degraded status
immediately and within the probe's timeout window, while liveness stays
healthy if the process itself is fine. Confirm the orchestrator actually
stops routing traffic to the instance during the simulated outage and
resumes once the dependency recovers.
