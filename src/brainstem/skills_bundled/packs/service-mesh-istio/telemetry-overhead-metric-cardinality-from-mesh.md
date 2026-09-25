---
name: telemetry-overhead-metric-cardinality-from-mesh
description: Enabling Istio's default telemetry generates a metric cardinality explosion in the monitoring backend because per-request labels include high-cardinality dimensions.
triggers: ["istio telemetry too many metrics", "envoy metrics cardinality explosion", "istio prometheus metrics too expensive", "mesh telemetry overwhelming monitoring backend"]
permissions: ["READ"]
---

## Symptom

After enabling Istio's default telemetry (metrics automatically generated
by Envoy sidecars for every service-to-service call), the metrics
backend (Prometheus, a hosted monitoring service) experiences a sharp
increase in time-series count and/or cost, sometimes severe enough to
destabilize the monitoring system itself.

## Likely causes

- **Istio's default telemetry labels include high-cardinality dimensions**
  (source/destination workload, revision, response code details, and in
  some configurations, per-request identifiers) that multiply out to a
  very large number of unique time series, especially in a mesh with many
  services and versions.
- **No telemetry customization was applied to reduce label cardinality**
  for the specific environment's scale -- the defaults are reasonable for
  smaller meshes but don't automatically adjust for a mesh with hundreds
  of services and frequent deployments (each new revision potentially
  creating new label value combinations).
- **Istio's telemetry API allows scoping/customizing which labels are
  emitted per-workload or mesh-wide**, but this wasn't configured,
  leaving every proxy emitting the full default label set regardless of
  whether the monitoring backend can afford that cardinality.
- **A metrics backend scrape/retention configuration wasn't adjusted for
  the mesh's actual telemetry volume**, compounding the cardinality issue
  with an also-undersized ingestion/storage pipeline.

## Diagnose

1. Query the monitoring backend for time-series count attributable to
   Istio/Envoy-generated metrics specifically, and identify which
   specific metric names and labels contribute the most unique series.
2. Check Istio's `Telemetry` API configuration (or lack thereof) for
   whether any label customization/reduction has been applied.
3. Correlate cardinality growth with mesh growth (new services, new
   revisions/versions deployed) to confirm the scaling relationship,
   distinguishing "expected growth at this mesh size" from "a specific
   misconfiguration."
4. Check whether specific high-cardinality labels (particularly anything
   derived from per-request or per-instance identifiers rather than
   stable dimensions) are present in the emitted metrics.

## Fix

Use Istio's `Telemetry` API to customize which metrics and labels are
emitted, dropping or aggregating high-cardinality dimensions that aren't
actually needed for the monitoring use cases in place, scoped mesh-wide
or per-namespace/workload as appropriate. Where fine-grained per-request
detail is genuinely needed for debugging, route it to a tracing/logging
system rather than a metrics backend, since metrics systems are
fundamentally not designed for high-cardinality dimensions the way
tracing systems are. Size the metrics backend's ingestion/retention
configuration appropriately for the mesh's actual, intentionally-reduced
telemetry volume.

## Pitfalls

Don't disable Istio telemetry entirely in response to a cost/cardinality
problem -- mesh-level telemetry (latency, error rate, traffic volume per
service pair) is one of the most valuable operational benefits of
running a service mesh; the fix is scoping it appropriately, not losing
it. Also don't reduce cardinality so aggressively that genuinely useful
per-service-pair visibility is lost -- balance cost against the specific
dimensions that matter for the organization's actual monitoring/alerting
needs.

## Verify

After applying telemetry customization, confirm the metrics backend's
time-series count/cost drops to an acceptable, sustainable level, and
confirm the specific dashboards/alerts the team actually relies on still
have the label granularity they need to function correctly.
