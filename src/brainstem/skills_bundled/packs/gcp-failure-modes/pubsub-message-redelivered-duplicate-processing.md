---
name: pubsub-message-redelivered-duplicate-processing
description: A Pub/Sub subscriber processes the same message more than once because acknowledgment didn't happen within the ack deadline, and the handler isn't idempotent.
triggers: ["pubsub message processed twice", "pubsub duplicate delivery", "pubsub ack deadline exceeded", "pub sub at least once duplicate"]
permissions: ["READ"]
---

## Symptom

A Pub/Sub-consuming application shows evidence of processing the same
logical message more than once (duplicate database inserts, a duplicate
downstream side effect like a duplicate email sent) despite Pub/Sub
supposedly having delivered the message and the subscriber supposedly
processing it successfully.

## Likely causes

- **The message handler takes longer to process than the subscription's
  acknowledgment deadline**, so Pub/Sub assumes delivery failed and
  redelivers the message to another (or the same) subscriber while the
  original handler is still working -- Pub/Sub's at-least-once delivery
  guarantee means this is expected behavior, not a bug in Pub/Sub itself.
- **The message handler isn't idempotent** -- it performs a side effect
  (an insert, an external API call) without checking whether that
  specific message was already processed, so redelivery directly causes
  duplicate effects.
- **The application acknowledges the message too early** (before the
  actual processing/side effect completes) in an attempt to avoid
  deadline issues, which can mask failures (an ack without the work
  actually succeeding) rather than fixing redelivery-driven duplication.
- **A subscriber crashes or is redeployed mid-processing** after starting
  work but before acknowledging, which is a normal, expected trigger for
  redelivery under at-least-once semantics, but only causes visible
  duplication if the handler isn't idempotent.

## Diagnose

1. Check the subscription's configured acknowledgment deadline against
   the handler's actual typical and worst-case processing time, using
   Pub/Sub's monitoring metrics for message processing duration and
   redelivery/duplicate counts.
2. Check whether the handler extends the ack deadline (`modifyAckDeadline`
   / an equivalent SDK call) for long-running processing, or relies on a
   single fixed deadline that a slow run could exceed.
3. Confirm whether the handler has any idempotency mechanism at all (a
   check against a processed-message-ID log, an idempotency key on the
   downstream operation) by reading its implementation.
4. Reproduce by manually redelivering a message (Pub/Sub supports this,
   or simulate by publishing a duplicate with the same logical content)
   and observe whether the duplicate side effect actually occurs.

## Fix

Make message handlers idempotent by design -- track processed message
IDs (Pub/Sub provides a message ID, or use an application-level
idempotency key from the message payload) and skip reprocessing a
message that's already been handled, or make the downstream operation
itself naturally idempotent (an upsert instead of an insert, a
deduplicating API call). For handlers with legitimately variable
processing time, extend the ack deadline programmatically for long-
running work rather than relying on a single static deadline sized for
the worst case. Never acknowledge a message before its associated work
has actually and durably completed, since an early ack combined with a
subsequent crash would lose the message entirely rather than just
duplicating it.

## Pitfalls

Don't try to "solve" at-least-once delivery by assuming exactly-once
semantics are achievable without deliberate idempotency work -- Pub/Sub's
standard delivery model is inherently at-least-once (Pub/Sub does offer
an exactly-once delivery feature in some configurations, but even that
has specific scope/limitations worth confirming rather than assuming
blanket exactly-once behavior). Also don't extend ack deadlines
indefinitely as a workaround for a handler that's simply too slow --
address the actual processing time if it's the root cause of chronic
near-deadline redeliveries.

## Verify

Deliberately redeliver a message (or simulate a slow handler exceeding
the original deadline) and confirm the downstream side effect occurs
exactly once despite the redelivery, proving the idempotency mechanism
works. Monitor Pub/Sub's redelivery/duplicate metrics over time to
confirm the rate of actual observed duplicate side effects (not just
redeliveries, which are expected) drops to zero.
