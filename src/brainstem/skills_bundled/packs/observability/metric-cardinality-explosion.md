---
name: metric-cardinality-explosion
description: A metrics backend (Prometheus, Datadog, etc.) slows down, drops data, or its cost spikes because a metric's label combinations grew far beyond what the time-series database can handle.
triggers: ["prometheus out of memory", "cardinality explosion", "too many time series", "metrics backend slow", "datadog custom metrics cost"]
permissions: ["READ"]
---

## Symptom

A metrics backend (Prometheus, VictoriaMetrics, Datadog, CloudWatch)
starts using dramatically more memory/disk than before, queries against a
specific metric time out or become extremely slow, ingestion starts
getting rejected/rate-limited, or a custom-metrics cost line item spikes --
often traced to one or a handful of specific metric names.

## Likely causes

- **A label was added with unbounded or high-cardinality values** --
  `user_id`, `request_id`, `session_id`, `email`, a raw URL path with
  path parameters unstripped (`/users/12345/orders/98765` instead of
  `/users/:id/orders/:id`) -- each distinct value creates an entirely new
  time series.
- **A metric is emitted per-instance with an ephemeral identifier as a
  label** -- container/pod IDs or hostnames in an autoscaling or
  frequently-redeployed environment, where every scale event or deploy
  creates a fresh set of series that the old ones never get cleaned up
  from.
- **Multiplicative label combinations** -- several individually
  reasonable-cardinality labels (e.g. `status_code` x `endpoint` x
  `region` x `client_version`) combine multiplicatively into a series
  count far larger than any one label suggested on its own.
- **A histogram or summary metric's bucket/quantile configuration is too
  fine-grained**, multiplying the underlying series count per bucket on
  top of whatever label cardinality already exists.

## Diagnose

1. Identify the specific metric(s) responsible -- most TSDBs expose a way
   to rank metrics by series count (Prometheus: `topk` on
   `count by (__name__)({__name__=~".+"})` or `prometheus_tsdb_*` internal
   metrics; vendor tools usually have a built-in cardinality/usage report).
2. For the worst offender, inspect its label set and estimate cardinality
   per label independently, then check whether the actual series count
   matches the product of per-label cardinalities (multiplicative
   combination) or is dominated by one specific label.
3. Check whether the suspect label's values look like identifiers (UUIDs,
   raw paths with embedded IDs, timestamps) rather than a bounded
   enumeration (a status code, a fixed set of region names).
4. Correlate the onset of the explosion with a deploy or config change
   that added or modified this metric's labels.

## Fix

Remove or replace unbounded-identifier labels with bounded ones: use a
normalized route template instead of the raw path, drop per-instance
ephemeral IDs from metric labels entirely (put them in logs/traces
instead, where high cardinality is expected and handled differently), and
push anything that's genuinely per-entity (per-user, per-request) into
the log/trace pipeline rather than the metrics pipeline -- metrics are for
aggregatable, bounded dimensions; logs and traces are for high-cardinality
detail. For multiplicative label combinations, question whether every
label combination is actually queried in practice -- if `client_version` x
`region` is never queried together, consider whether both need to be on
the same metric, or whether one belongs on a separate, coarser metric.

## Pitfalls

Don't fix this by simply dropping data retention or downsampling faster --
that reduces the symptom's visible cost without addressing why the series
count is unbounded in the first place, and the next redeploy/scale event
reproduces the same explosion. Also watch for the inverse mistake after
fixing this once: removing a label that turns out to be genuinely needed
for a specific known query (e.g., debugging per-version regressions) --
check real dashboard/alert queries for the label before removing it, not
just its cardinality in isolation.

## Verify

Confirm the specific metric's series count drops to an expected, bounded
range after the fix (compare against the TSDB's own cardinality report,
not just "it feels faster"), and confirm ingestion/memory/cost metrics for
the backend itself return to baseline. Re-check after the next deploy or
autoscaling event specifically, since ephemeral-ID-driven explosions often
only reproduce on exactly that trigger.
