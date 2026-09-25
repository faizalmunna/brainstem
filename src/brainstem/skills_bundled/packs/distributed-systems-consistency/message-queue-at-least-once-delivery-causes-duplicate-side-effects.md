---
name: message-queue-at-least-once-delivery-causes-duplicate-side-effects
description: A consumer processes the same queued message more than once because the broker's at-least-once delivery guarantee redelivers it after an ack is lost or delayed.
triggers: ["message processed twice from queue", "duplicate event handling sqs kafka", "at least once delivery causing duplicates", "consumer redelivered message after timeout"]
permissions: ["READ"]
---

## Symptom

A message queue or event stream (SQS, RabbitMQ, Kafka, Pub/Sub) is
configured with its default or expected at-least-once delivery
guarantee, and a consumer occasionally processes the exact same
message twice, causing a duplicated side effect -- two emails sent,
a counter incremented twice, a record inserted twice. The message
itself wasn't duplicated by anything malicious or buggy in the
producer; this is the delivery guarantee working as documented, but
the consumer wasn't built to handle it.

## Likely causes

- **The consumer's processing takes longer than the visibility
  timeout / ack deadline**, so the broker assumes the message was
  never picked up (or the consumer died) and redelivers it to another
  consumer while the first one is still legitimately working on it.
- **The consumer crashes or is redeployed after completing the side
  effect but before sending the acknowledgment**, so from the broker's
  perspective the message was never successfully processed, and it's
  redelivered on schedule even though the effect already happened.
- **Consumer-group rebalancing (Kafka) or connection loss (RabbitMQ)
  happens mid-processing**, causing in-flight messages to be
  reassigned to a different consumer instance that has no knowledge
  the original instance already started (or finished) processing
  them.
- **The application's processing logic isn't idempotent and was built
  under an implicit exactly-once assumption**, even though the broker
  in use only ever advertised at-least-once (or effectively-once with
  caveats) semantics -- this is the same underlying data point as the
  visibility-timeout case, but the fix is different: the guarantee was
  never violated, the code's assumption was wrong from the start.

## Diagnose

1. Confirm the broker's actual delivery guarantee for the configuration
   in use (SQS standard queue vs FIFO, Kafka consumer commit strategy,
   RabbitMQ ack mode) -- don't assume; check the specific settings,
   since some configurations look exactly-once-ish but aren't under
   failure.
2. Compare the consumer's typical and p99 processing duration against
   the configured visibility timeout / session timeout -- if p99
   exceeds the timeout even occasionally, redelivery during normal
   operation (not just crashes) is expected.
3. Check consumer logs/metrics for redeployment, crash, or rebalance
   events coincident with known duplicate-processing incidents, to
   distinguish "ack was lost due to a crash" from "message was simply
   slow."
4. Check whether message IDs (or a natural dedup key in the payload)
   are logged on processing, and search logs for the same ID
   appearing in two separate processing attempts to confirm true
   duplication versus a look-alike but distinct event.
5. Review the processing code path for any side effect that isn't
   naturally idempotent (an increment, an append, a non-idempotent
   external API call) versus one that already is (a `SET` to an
   absolute value, an upsert keyed by message ID).

## Fix

Make message processing idempotent by design: derive a stable dedup
key from the message (a message ID the broker provides, or a
business-meaningful key from the payload) and record it durably
*before or atomically with* performing the side effect, using a
unique constraint so a redelivered message's second attempt is
detected and skipped rather than reprocessed -- the same atomic-claim
pattern used for idempotency keys generally. Size the visibility
timeout / ack deadline against measured p99 (not average) processing
time, and for jobs whose duration is unpredictable, use the broker's
heartbeat/extend-visibility mechanism to renew it while still working,
rather than picking one static value. Structure the consumer so the
acknowledgment happens only after the side effect (or its durable
dedup record) is confirmed committed, and prefer patterns where the
ack and the effect are as close to atomic as the broker and datastore
allow (e.g. commit offset only after a transactional outbox write
succeeds).

## Pitfalls

Don't treat "switch to a FIFO/exactly-once-configured queue" as a
complete fix on its own -- most brokers' "exactly-once" modes only
cover specific parts of the pipeline (e.g. Kafka's exactly-once
semantics apply within Kafka-to-Kafka processing, not to an arbitrary
external side effect the consumer performs), so an external API call
or database write triggered by the message still needs its own
idempotency handling regardless of the queue's delivery mode. Also
don't build the dedup check as a separate non-atomic step from the
side effect (check a "processed" set, then perform the effect, then
mark it) -- that reintroduces the same check-then-act race that
idempotency keys are meant to solve.

## Verify

Write a test that delivers the same message twice in a row to the
consumer (simulating redelivery directly, not by waiting for a real
timeout) and assert the side effect's downstream state shows exactly
one occurrence. Separately, run a load test that forces the
consumer's processing time past the configured visibility timeout on
a fraction of messages and confirm the resulting redeliveries are
correctly deduplicated rather than producing duplicate effects.
