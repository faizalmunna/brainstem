---
name: exactly-once-semantics-duplicate-on-rebalance
description: A Kafka consumer configured for exactly-once-style processing still produces duplicate side effects during a consumer group rebalance because offset commits and processing aren't actually atomic.
triggers: ["kafka duplicate processing after rebalance", "exactly once semantics not working kafka", "kafka offset commit race duplicate", "consumer rebalance causes reprocessing"]
permissions: ["READ"]
---

## Symptom

Despite configuring a Kafka consumer for what the team believes is
exactly-once processing, duplicate side effects (duplicate database
writes, duplicate downstream events) are observed specifically around
consumer group rebalance events (a consumer instance joining, leaving, or
a deploy restarting consumers), even though the same messages don't
duplicate during steady-state operation.

## Likely causes

- **The application processes a message and commits its offset as two
  separate, non-atomic steps**, and a rebalance occurring between
  processing and committing causes the partition to be reassigned to
  another consumer, which reprocesses the same message because the
  offset was never actually committed.
- **"Exactly-once" was assumed from Kafka's own delivery guarantees
  alone, without implementing idempotent processing or transactional
  writes on the application/consumer side** -- Kafka's exactly-once
  semantics (via transactions/idempotent producers) covers specific
  produce-side and Kafka-Streams scenarios, not automatically an
  arbitrary consumer's external side effects (a database write, an API
  call) unless the consumer explicitly participates in that transactional
  model.
- **Offset commits are configured with `enable.auto.commit=true` on a
  timer**, decoupling the commit from actual processing completion --
  a message can be committed as "done" before its side effect is durably
  applied, or reprocessed after its side effect already happened but
  before the timer-based commit fired.
- **A rebalance listener isn't implemented to handle in-flight message
  state correctly** -- partitions revoked mid-processing don't have a
  clean way to know whether the in-flight message's side effect
  completed before the revocation, without explicit handling.

## Diagnose

1. Reproduce a rebalance deliberately (restart a consumer instance, add a
   new one to the group) while the consumer is actively processing
   messages, and check for duplicate side effects specifically correlated
   with that rebalance window.
2. Check the consumer's commit strategy (`enable.auto.commit` setting,
   or explicit manual commit calls) and confirm precisely where in the
   processing flow commits actually happen relative to the side effect.
3. Check whether the downstream side effect (database write, API call)
   has any idempotency mechanism (a unique constraint, an idempotency
   key) independent of Kafka's own guarantees.
4. Review whether a `ConsumerRebalanceListener` (or equivalent) is
   implemented to handle partition revocation cleanly, or whether
   in-flight state is simply abandoned on rebalance.

## Fix

Make the downstream side effect itself idempotent (a database upsert
keyed on a unique message identifier, a deduplication check before
producing a downstream event) so a reprocessed message due to a
rebalance produces the same end state rather than a duplicate effect --
this is the most robust fix since it doesn't depend on perfectly
eliminating reprocessing, only on tolerating it safely. Switch from
auto-commit to manual commit performed only after the side effect is
confirmed durably complete, minimizing (though not eliminating) the
reprocessing window. Implement a rebalance listener that completes or
safely aborts in-flight work before releasing a partition, where the
processing framework supports it.

## Pitfalls

Don't assume enabling Kafka's transactional/exactly-once producer
features alone solves this for a typical consumer with external side
effects -- those features solve a narrower, specific class of problem
(exactly-once within Kafka-to-Kafka pipelines, particularly Kafka
Streams); a consumer writing to an external database or calling an
external API needs its own idempotency strategy regardless. Also don't
rely solely on reducing the rebalance window (faster commits) as the fix
without idempotency -- rebalances can still occur at exactly the wrong
moment no matter how small the window is.

## Verify

Deliberately trigger a rebalance during active processing in a test
environment (with instrumented, countable side effects) and confirm the
end state is correct (no duplicate real-world effect) even though the
message may have been technically reprocessed at the Kafka level.
Confirm the idempotency mechanism itself doesn't silently swallow a
genuinely new message that happens to share an identifier incorrectly.
