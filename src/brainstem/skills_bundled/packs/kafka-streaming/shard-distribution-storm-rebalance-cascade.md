---
name: shard-distribution-storm-rebalance-cascade
description: A streaming service's automatic shard/partition rebalancing cascades into a distribution storm after a migration leaves an uneven number of low-throughput shards.
triggers: ["kafka partition rebalance storm", "kinesis shard distribution overload", "streaming service rebalance cascade", "uneven shard distribution after migration"]
permissions: ["READ"]
---

## Symptom

After a cluster migration, a scaling event, or a resharding operation,
a streaming platform (Kafka, or an equivalent managed streaming service)
enters a period of sustained instability -- continuous partition/shard
rebalancing, elevated latency, and consumer lag -- that doesn't settle
even well after the triggering event completed, because the rebalancing
process itself is generating enough load to trigger further rebalancing.

## Likely causes

- **A migration or resharding operation left an unusually large number of
  low-throughput shards/partitions relative to what's normal**, and the
  overhead of managing/rebalancing that many small units (metadata
  operations, leader elections, status message processing) becomes
  disproportionate to the actual data throughput they carry.
- **Rebalancing status/coordination messages between service instances
  were misinterpreted or processed inefficiently at the new, larger
  shard count**, causing the coordination layer itself to become
  overloaded and trigger further corrective rebalancing in a feedback
  loop.
- **Consumer group rebalancing (in Kafka specifically) is triggered
  repeatedly because consumers are timing out or being evicted from the
  group during the period of elevated latency**, and each rebalance
  itself causes a pause in consumption that increases lag, which can
  trigger yet another rebalance under an aggressive session-timeout
  configuration.
- **No circuit breaker or backoff exists on the automatic rebalancing/
  resharding logic itself**, so once triggered, the corrective mechanism
  keeps firing based on symptoms that are actually caused by its own
  previous corrective actions, rather than settling.

## Diagnose

1. Reconstruct the shard/partition count and distribution before and
   after the triggering migration/resharding event, looking specifically
   for a large increase in low-throughput units relative to before.
2. Check coordination/rebalancing event logs for frequency -- a
   healthy system rebalances occasionally in response to genuine load
   changes; a storm shows rebalancing recurring far more frequently than
   the underlying data volume changes would justify.
3. For Kafka specifically, check consumer group rebalance frequency and
   correlate with consumer session timeout and heartbeat configuration
   relative to observed processing latency during the incident.
4. Check whether rebalancing operations themselves show up as a
   significant load source in cluster-level metrics (CPU, network,
   coordination-service load) during the storm, confirming the
   self-reinforcing feedback loop hypothesis.

## Fix

Consolidate an excessive number of low-throughput shards/partitions back
to a count proportional to actual data volume needs, rather than leaving
an artifact of a migration in place. Add backoff/circuit-breaking to
automatic rebalancing logic so it doesn't retrigger immediately based on
symptoms it just caused itself. For Kafka consumer groups specifically,
tune session timeout and heartbeat interval to tolerate transient latency
spikes without triggering an unnecessary rebalance, and ensure consumers
process messages within their session timeout even under moderate
backpressure. Where a managed streaming service handles resharding
automatically, monitor and manually intervene (consolidating shards) if
an automated resharding event produces an unexpectedly fragmented
distribution.

## Pitfalls

Don't respond to a rebalance storm by disabling automatic rebalancing/
resharding entirely -- that removes a mechanism that's usually load-
bearing for handling genuine, legitimate load changes; fix the specific
feedback loop (excessive shard count, timeout tuning) instead of removing
the corrective mechanism altogether. Also don't scale shard count up
aggressively "to be safe" after this incident -- overcorrecting toward
too many shards reproduces the same class of problem from a different
direction.

## Verify

Monitor shard/partition count and rebalancing event frequency over a
period following the fix and confirm both settle to levels proportional
to actual data volume with no recurring storm pattern. Deliberately
trigger a moderate, legitimate scaling event in a non-production
environment and confirm rebalancing completes and settles within an
expected, bounded time rather than cascading.
