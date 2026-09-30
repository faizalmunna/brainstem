---
name: pubsub-message-loss-no-persistence-guarantee
description: Messages published via Redis Pub/Sub are silently lost for any subscriber that wasn't actively connected at the moment of publish, because Pub/Sub provides no persistence or replay.
triggers: ["redis pubsub message lost", "subscriber missed message redis", "redis pub sub not reliable", "pub sub message delivery guarantee redis"]
permissions: ["READ"]
---

## Symptom

An application using Redis Pub/Sub for inter-service messaging discovers
that messages are missed by a subscriber that was briefly disconnected,
restarting, or not yet fully initialized at the exact moment a message
was published -- there's no way to retrieve the missed message
afterward, and the team is surprised this is expected behavior rather
than a bug.

## Likely causes

- **Redis Pub/Sub is fundamentally fire-and-forget with no persistence**
  -- a message published while no subscriber is connected (or while a
  subscriber's connection is momentarily down) is simply gone; Pub/Sub
  was never designed to guarantee delivery or support replay, unlike a
  proper message queue or log-based streaming system.
- **A subscriber's brief disconnection (a deploy, a network blip, a
  restart) creates a window where published messages during that window
  are permanently lost**, and if the application's design assumed at-
  least-once delivery (common for queue/messaging systems), this
  assumption is simply wrong for Redis Pub/Sub specifically.
- **Redis Pub/Sub was chosen for a use case that actually needed
  durability/replay** (an event notification system where missing an
  event has real consequences) rather than for its actual best fit
  (ephemeral, best-effort notifications where an occasional missed
  message is genuinely acceptable, like a "someone is typing" indicator).
- **No fallback/reconciliation mechanism exists** to detect and recover
  from a missed message, such as periodically polling for authoritative
  state to catch anything a missed Pub/Sub notification would have
  conveyed.

## Diagnose

1. Confirm the actual delivery guarantee being relied upon in the
   application design versus what Redis Pub/Sub actually provides (none,
   by design) -- this is usually a design-assumption gap, not a bug to
   "fix" in Redis itself.
2. Identify the specific disconnection/restart events correlating with
   reported missed messages, confirming the pattern matches Pub/Sub's
   known at-most-once, no-persistence behavior.
3. Assess the actual business impact of a missed message for this
   specific use case -- some uses genuinely tolerate occasional loss,
   others don't, and that assessment determines whether Pub/Sub is even
   the right tool.
4. Check whether Redis Streams (a different, persistent, replay-capable
   feature within Redis) was considered as an alternative during the
   original design, or whether Pub/Sub was chosen without this
   distinction being understood.

## Fix

For use cases that genuinely need delivery guarantees and replay
capability, migrate from Redis Pub/Sub to Redis Streams (which persists
messages in a log and supports consumer groups with acknowledgment,
much closer to a real message queue's semantics) or an actual message
queue/streaming platform (Kafka, RabbitMQ, SQS) suited to the durability
requirement. For use cases where occasional message loss is genuinely
acceptable (ephemeral real-time notifications), keep Pub/Sub but add a
reconciliation mechanism -- a periodic poll of authoritative state that
would catch anything a missed notification should have conveyed -- so a
missed message degrades to slightly-delayed correctness rather than
permanently incorrect state.

## Pitfalls

Don't try to retrofit delivery guarantees onto Redis Pub/Sub itself
(client-side acknowledgment hacks, manual replay buffers) -- these add
complexity while still fundamentally fighting against what the primitive
is designed for; if durability is genuinely required, use a primitive
that actually provides it (Redis Streams or a dedicated queue) instead.

## Verify

For a Streams-based migration, deliberately disconnect a consumer,
publish messages during the disconnection, reconnect, and confirm the
consumer can retrieve the missed messages from the stream. For a
reconciliation-based fix on top of Pub/Sub, deliberately miss a
notification and confirm the periodic reconciliation poll independently
catches and corrects the resulting state gap within an acceptable time
window.
