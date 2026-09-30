---
name: envoy-sidecar-resource-limit-cpu-throttling
description: Application latency increases mesh-wide after sidecar injection because the Envoy sidecar's own CPU limit is undersized and gets throttled under load.
triggers: ["istio sidecar adding latency", "envoy proxy cpu throttled", "mesh overhead high latency", "sidecar resource limits too low"]
permissions: ["READ"]
---

## Symptom

After enabling Istio sidecar injection for a service, its observed
latency increases noticeably, and the increase is disproportionate to
what's typically expected from proxy overhead alone -- investigation
eventually points at the Envoy sidecar container itself being CPU-
throttled under load.

## Likely causes

- **The Envoy sidecar's CPU request/limit was left at a default or
  arbitrarily small value** that doesn't scale with the actual traffic
  volume the application handles, so under real load the proxy itself
  becomes CPU-constrained and adds queueing delay processing requests.
- **A cluster-wide default sidecar resource setting was applied
  uniformly** to services with very different traffic profiles, sized
  appropriately for a low-traffic service but insufficient for a
  high-traffic one.
- **CPU limits (not just requests) are set tightly**, and Kubernetes'
  CFS (Completely Fair Scheduler) throttling kicks in even when average
  CPU usage looks acceptable, because usage is bursty and hits the limit
  during short windows that don't show up clearly in average-based
  metrics.
- **Additional Istio features (mTLS, telemetry generation, complex
  routing/authorization policy evaluation) enabled without a
  corresponding increase in sidecar resource allocation** add real CPU
  cost per request that wasn't accounted for when resources were
  originally sized.

## Diagnose

1. Check the Envoy sidecar container's specific CPU usage and throttling
   metrics (Kubernetes exposes CFS throttling stats per container)
   during the periods of elevated latency, not just the application
   container's metrics.
2. Compare the sidecar's configured CPU request/limit against its actual
   peak (not average) usage under realistic load.
3. Correlate latency increases with specific Istio features being
   enabled/changed (a new authorization policy, increased telemetry
   verbosity) to identify whether a recent configuration change added
   proxy-side CPU cost.
4. Test with the sidecar's CPU limit temporarily increased in a non-prod
   environment under the same load, and confirm whether latency improves,
   directly validating throttling as the cause.

## Fix

Size the Envoy sidecar's CPU request/limit based on the specific
service's actual traffic profile and peak usage, not a uniform cluster
default -- higher-traffic services need proportionally more sidecar
resources. Consider raising or removing the CPU limit (while keeping an
appropriate request) if CFS throttling on bursty traffic is the specific
issue, accepting the tradeoff of potentially higher resource consumption
during bursts. Where a specific added Istio feature is responsible for
increased per-request CPU cost, weigh that feature's value against its
resource cost and adjust sidecar sizing accordingly rather than leaving
it under-provisioned.

## Pitfalls

Don't over-provision sidecar resources uniformly across every service as
a blanket fix -- that wastes cluster capacity for genuinely low-traffic
services; size per-service based on actual measured needs. Also don't
conflate proxy CPU throttling with an application-level performance
issue -- misdiagnosing this as an application bug and spending time
there instead of the sidecar's resource configuration wastes
investigation effort in the wrong place.

## Verify

After adjusting sidecar resource allocation, monitor CFS throttling
metrics for the sidecar container under the same realistic load and
confirm throttling drops to negligible levels, with overall request
latency returning to the expected baseline for a mesh-enabled service.
