---
name: consumer-lag-single-threaded-bottleneck
description: A Kafka consumer group falls progressively further behind the log even though the cluster has ample throughput headroom, because message processing is effectively single-threaded per partition.
triggers: ["kafka consumer lag growing", "consumer cannot keep up with kafka", "kafka partition processing bottleneck", "consumer group falling behind"]
permissions: ["READ"]
---

## Symptom

Consumer lag (the gap between the latest produced offset and the
consumer's committed offset) for a Kafka topic grows steadily over time,
even though the Kafka cluster itself shows plenty of unused broker
capacity and producers aren't experiencing any backpressure -- the
bottleneck is clearly on the consuming side, not the cluster.

## Likely causes

- **Kafka's consumption model processes each partition sequentially
  within a single consumer instance's assigned partitions**, so if
  message processing per record is slow (a synchronous downstream call,
  expensive computation) and there aren't enough partitions/consumer
  instances to parallelize across, throughput is capped regardless of
  cluster capacity.
- **The topic has too few partitions relative to the desired consumption
  parallelism** -- Kafka consumer parallelism within a consumer group is
  fundamentally bounded by partition count, so even adding more consumer
  instances beyond the partition count provides no additional throughput.
- **A single slow partition (a hot key concentrating disproportionate
  traffic, or a partition assigned to an unusually loaded consumer
  instance) drags down overall group lag** even if other partitions are
  keeping up fine, and aggregate lag metrics can mask this per-partition
  imbalance.
- **Processing logic added a new expensive step (a synchronous external
  API call, added validation) without corresponding capacity/parallelism
  increases**, gradually pushing what used to be comfortably fast
  processing into a bottleneck as message volume or processing cost grew.

## Diagnose

1. Check per-partition lag (not just aggregate consumer-group lag) to
   identify whether lag is evenly distributed or concentrated on specific
   partitions, which points at either a hot key or an uneven consumer
   assignment.
2. Check the topic's partition count against the number of active
   consumer instances in the group -- if partition count is the limiting
   factor, adding consumers won't help until partitions increase.
3. Profile actual per-message processing time in the consumer application
   to identify whether processing itself (not Kafka fetch/network) is the
   bottleneck, and whether a specific recently-added step is responsible.
4. Check cluster-level broker metrics (CPU, disk I/O, network) to confirm
   the cluster genuinely has headroom, ruling out a cluster-side capacity
   issue as a contributing factor.

## Fix

Increase the topic's partition count (a one-way operation for existing
topics -- plan the target count based on realistic future scale, since
you can't reduce partition count later) to allow more consumer
parallelism, paired with adding proportionally more consumer instances.
For processing-time bottlenecks, parallelize within a single consumer's
partition processing where message ordering doesn't strictly require
sequential processing (dispatching to a thread/worker pool per partition
rather than blocking on each message), or move expensive synchronous work
(external API calls) to an async pattern that doesn't block the main
consume loop. For a hot-key-driven imbalance, consider a partitioning key
strategy that distributes load more evenly, if message ordering
requirements allow it.

## Pitfalls

Don't add partitions far beyond what's needed for current+near-future
scale just to be safe -- more partitions means more open file handles,
more replication overhead, and more per-partition metadata cost cluster-
wide, so pick a partition count based on a realistic capacity plan, not
an arbitrarily large number. Also, when parallelizing message processing
within a partition, be careful about breaking ordering guarantees the
application may depend on -- verify whether strict per-key ordering
actually matters for correctness before introducing concurrent
processing within a partition.

## Verify

After the fix, monitor per-partition and aggregate consumer lag over a
period covering normal peak load and confirm lag stabilizes or trends
toward zero rather than continuing to grow. Confirm message ordering
guarantees (if required by the application) are still correctly
maintained after any concurrency changes to processing logic.
