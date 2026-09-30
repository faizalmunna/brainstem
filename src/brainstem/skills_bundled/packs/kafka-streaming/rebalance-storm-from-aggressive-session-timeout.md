---
name: rebalance-storm-from-aggressive-session-timeout
description: A Kafka consumer group repeatedly rebalances because session timeout and max poll interval settings are too aggressive relative to actual message processing time, not because of any real instance failure.
triggers: ["kafka consumer group constantly rebalancing", "max.poll.interval.ms exceeded", "session timeout too aggressive kafka", "consumer keeps getting kicked from group"]
permissions: ["READ"]
---

## Symptom

A Kafka consumer group rebalances far more frequently than any actual
consumer instance failure or deployment would explain -- healthy
consumer instances are repeatedly evicted from the group and have to
rejoin, causing recurring processing pauses and lag spikes with no
underlying infrastructure problem.

## Likely causes

- **`max.poll.interval.ms` is set lower than the actual time a single
  poll's batch of messages can take to process**, so a consumer that's
  working correctly but processing a normal, sometimes-slower batch gets
  treated as unresponsive and evicted from the group, even though it was
  never actually stuck.
- **`session.timeout.ms` is set aggressively low to detect failures
  quickly**, but combined with normal GC pauses, network jitter, or
  broker-side load, healthy consumers occasionally miss a heartbeat
  window and get evicted for a transient blip rather than a genuine
  failure.
- **Message processing time has grown over time** (a new, slower
  processing step added, increased message volume per batch) without a
  corresponding review of timeout settings that were originally tuned
  for a faster processing path.
- **`max.poll.records` is set high relative to per-record processing
  time**, meaning a single poll can return a large batch that takes
  longer to fully process than the poll interval allows, even if
  per-record processing itself is reasonably fast.

## Diagnose

1. Check consumer group rebalance event frequency and correlate with
   actual consumer instance health (deploys, crashes, actual
   infrastructure issues) -- rebalances with no corresponding real
   failure event point at timeout misconfiguration.
2. Measure actual time-per-poll (from poll() call to the next poll()
   call) in the consumer application and compare directly against
   `max.poll.interval.ms`.
3. Check for GC pause logs or resource contention metrics around
   rebalance events, to determine if `session.timeout.ms` is being
   exceeded due to transient JVM/resource pressure rather than genuine
   unresponsiveness.
4. Check whether `max.poll.records` combined with actual per-record
   processing time regularly approaches or exceeds the poll interval
   budget.

## Fix

Increase `max.poll.interval.ms` to comfortably exceed the actual
worst-case time to process a full batch of `max.poll.records`, based on
measured data rather than a guess. Tune `session.timeout.ms` (and
`heartbeat.interval.ms`) to tolerate realistic transient jitter without
being so long that genuine failures take too long to detect -- this is a
real tradeoff, not a one-directional "always increase" fix. Where
per-record processing time is inherently variable or slow, consider
processing messages asynchronously relative to the poll loop (using a
separate thread pool) so the poll loop itself can call `poll()`
frequently enough to satisfy timeout requirements while actual processing
happens in the background, tracked separately for offset commit
correctness. Reduce `max.poll.records` if batch processing time is the
dominant factor and reducing batch size is otherwise acceptable.

## Pitfalls

Don't simply maximize all timeout values to eliminate rebalances
entirely -- that delays genuine failure detection significantly, meaning
a truly stuck or crashed consumer instance takes much longer to be
detected and have its partitions reassigned, directly hurting
availability during a real failure. Tune based on measured normal-case
behavior with reasonable headroom, not an arbitrary maximum.

## Verify

After retuning, monitor rebalance frequency over a period covering
normal processing variance (including any known periodic slow batches)
and confirm rebalances now correlate only with genuine consumer
instance changes (deploys, crashes), not spurious timeouts. Separately,
verify a genuinely stuck/crashed consumer is still detected and evicted
within an acceptable time window, confirming the tuning didn't sacrifice
real failure detection for rebalance-storm avoidance.
