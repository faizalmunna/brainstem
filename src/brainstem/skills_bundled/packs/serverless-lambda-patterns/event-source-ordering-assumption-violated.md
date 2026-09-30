---
name: event-source-ordering-assumption-violated
description: A function's logic assumes ordered, exactly-once event delivery, but the event source actually delivers out of order or at-least-once.
triggers: ["s3 events out of order", "lambda processing duplicate events", "eventbridge events arrive twice", "race condition between create and delete events serverless"]
permissions: ["READ"]
---

## Symptom
A function that reacts to S3 object events, EventBridge rules, SNS
notifications, or similar occasionally produces results that only make
sense if two events were processed in the wrong order or the same event
was processed twice: a record that should have been deleted reappears
because a "create" event was handled after a later "delete" event, a
downstream side effect (an email, a charge, a counter increment) fires
twice for what the user did once, or a resource ends up in a state that
implies stale data overwrote fresher data.

## Likely causes
1. **The event source provides at-least-once delivery, not exactly-once**
   (true of S3 event notifications, SNS, EventBridge, and SQS without
   FIFO), so the same logical event can be delivered to the function more
   than once -- most commonly after a retry following a transient error
   or timeout on a previous delivery attempt that actually succeeded
   before failing to acknowledge.
2. **The event source provides no ordering guarantee across events for
   different keys/objects, and sometimes not even for the same key**
   (standard SQS and most S3 event notification patterns don't guarantee
   order), so a "create then immediately delete" or "update A then update
   B" sequence can be delivered and processed in either order depending on
   which invocation happens to run first or retries.
3. **The handler's own logic implicitly assumes the event payload
   represents the current state of the world** (e.g., "this event says
   the object was created, so I'll insert a row") rather than treating the
   event as one data point to reconcile against current actual state,
   which breaks the moment a later event for the same key is processed
   first due to retries or concurrent invocations.
4. **Concurrent invocations processing events for the same logical entity
   race each other** -- because the platform can invoke the function
   concurrently for different events, two events about the same S3 key or
   database record can be mid-processing at the same time with no
   coordination, so whichever finishes last wins regardless of which
   event was semantically newer.
5. **No idempotency key or deduplication mechanism is used**, so
   duplicate deliveries aren't detected as duplicates at all -- the
   handler has no way to distinguish "this is the second delivery of an
   event I already processed" from "this is a new event," which is a
   prerequisite for handling at-least-once delivery correctly.

## Diagnose
- Check the event source's documented delivery guarantee explicitly
  (S3 event notifications: at-least-once, no ordering guarantee across
  different event types for overlapping keys; standard SQS: at-least-once,
  best-effort ordering; SNS: at-least-once) -- don't assume, confirm
  against the specific source in use, since guarantees differ meaningfully
  between FIFO and standard variants.
- Log the event's own timestamp/sequence field (e.g., S3's `eventTime`,
  a DynamoDB Stream's `ApproximateCreationDateTime`) alongside the
  function's own processing timestamp for a sample of events, and look
  for cases where processing order doesn't match event-time order --
  that's direct evidence of an ordering violation actually occurring, not
  just a theoretical risk.
- Grep logs for the same event ID (or the same S3 object key + event type)
  appearing in more than one invocation -- confirms duplicate delivery is
  happening, and check whether the handler's side effect (a write, an
  external call) was also duplicated as a result.
- Review the handler code for whether it reads-then-writes based on the
  event payload alone versus checking current stored state first --
  code that never re-reads current state before acting is structurally
  vulnerable to both duplicate and out-of-order delivery.
- If using DynamoDB Streams or Kinesis (which do guarantee order per
  shard/partition key), confirm events for the same logical entity are
  actually being routed to the same shard/partition key -- a partition
  key that doesn't match the entity's identity silently loses the
  ordering guarantee the source would otherwise provide.

## Fix
Make the handler idempotent and order-tolerant by design: store and check
an idempotency key (the event ID, or a content hash) before applying a
side effect, so a duplicate delivery is detected and skipped rather than
reapplied. For state that can be affected by out-of-order events, include
a version or timestamp comparison against currently stored state before
writing -- only apply the event if it's newer than what's stored (a
last-writer-wins-by-event-time pattern), so a stale, delayed event can't
overwrite a fresher one. Where the event source supports it, use ordering
guarantees deliberately (SQS FIFO with a message group ID per entity,
DynamoDB Streams/Kinesis with the entity ID as partition key) rather than
assuming a standard/unordered source will happen to arrive in order most
of the time. Treat every incoming event as "a hint that something may have
changed" and re-fetch authoritative current state when the decision is
consequential, rather than trusting the event payload as the sole source
of truth for anything beyond triggering the check.

## Pitfalls
Adding a naive "process each event ID only once" deduplication cache
without an eviction/TTL strategy grows unbounded and, if it's in-memory
per container, doesn't actually work across concurrent containers or
after a cold start -- durable, shared dedup state (a database row, a
DynamoDB conditional write) is required for it to hold under real
concurrency. Also, reaching for FIFO/ordered sources everywhere as a
blanket fix trades away throughput and adds operational complexity
(message group ID design, lower throughput ceilings) in cases where a
simpler idempotent-and-order-tolerant handler would have been sufficient.

## Verify
Deliberately replay a captured event twice through the function (or
re-drive it from a DLQ) and confirm the side effect (a database write, an
external call) is not duplicated; separately, construct a test where an
older event for the same entity is delivered after a newer one and
confirm the stored state reflects the newer event's data, not the older
one that arrived last.
