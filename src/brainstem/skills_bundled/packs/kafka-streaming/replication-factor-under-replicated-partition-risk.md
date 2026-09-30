---
name: replication-factor-under-replicated-partition-risk
description: A Kafka topic's partitions run under-replicated for an extended period without alerting, leaving data one broker failure away from loss or unavailability.
triggers: ["kafka under replicated partitions", "kafka replication factor risk", "partition replica out of sync", "kafka broker failure would lose data"]
permissions: ["READ"]
---

## Symptom

A Kafka cluster health check (or a broker failure incident) reveals that
some partitions have been running under-replicated (fewer in-sync
replicas than the topic's configured replication factor) for an extended
period, meaning the topic was effectively one more broker failure away
from data loss or unavailability, and nobody had been aware.

## Likely causes

- **A broker went offline (a crash, a maintenance operation left
  incomplete) and replicas hosted on it fell out of sync**, but no
  alerting exists on under-replicated partition count, so the condition
  persisted silently rather than being addressed promptly.
- **A broker is online but struggling under load (disk I/O saturation,
  network congestion) and can't keep its replicas caught up**, causing
  them to fall out of the in-sync replica set even though the broker
  process itself is technically running.
- **Replication factor was set too low for the topic's actual criticality**
  (e.g. replication factor 2, tolerating only a single broker failure)
  when the topic's importance actually warranted 3 or more, leaving less
  margin for error during any broker issue.
- **A cluster rebalance or broker replacement operation was started but
  not completed/monitored to completion**, leaving partitions
  mid-rebalance in an under-replicated state longer than intended.

## Diagnose

1. Check current under-replicated partition count and identify which
   specific brokers are involved (the same broker(s) repeatedly, or
   spread across the cluster) to distinguish a broker-specific issue from
   a cluster-wide one.
2. Check the history of under-replicated partition count over time (via
   monitoring, if it exists) to determine how long the condition has
   persisted, not just its current state.
3. For implicated brokers, check resource utilization (disk I/O, network,
   CPU) to determine whether they're offline entirely or online but
   struggling to keep up with replication.
4. Check the specific topics' configured replication factor against
   their actual business criticality to assess whether the configured
   factor itself is adequate.

## Fix

Set up alerting on under-replicated partition count (most Kafka
monitoring setups expose this as a standard metric) with a threshold low
enough to catch the condition promptly, since it's a leading indicator of
reduced fault tolerance, not just a lagging one. Address the root cause
for the specific implicated broker(s) -- bring an offline broker back
online and let it catch up, or address resource contention on a
struggling-but-online broker. Review replication factor for critical
topics and increase it if the current factor doesn't provide adequate
margin for the topic's actual importance, understanding the tradeoff in
additional storage and write overhead.

## Pitfalls

Don't treat "the cluster is still serving traffic" as evidence
everything is fine when under-replicated partitions exist -- the risk is
specifically about reduced fault tolerance for the *next* failure, which
won't be visible in current serving metrics until that failure actually
happens. Also don't increase replication factor for every topic
uniformly to maximum safety without considering the real storage/
throughput cost -- match replication factor to actual per-topic
criticality.

## Verify

After addressing the root cause, confirm under-replicated partition
count returns to zero (or the cluster's normal baseline) and stays there.
Confirm the new alerting actually fires in a deliberate test (simulate a
broker going offline in a non-production cluster) with enough lead time
to respond before a second failure could cause real data loss or
unavailability.
