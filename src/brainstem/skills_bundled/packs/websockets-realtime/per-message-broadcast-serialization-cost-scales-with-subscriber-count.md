---
name: per-message-broadcast-serialization-cost-scales-with-subscriber-count
description: CPU usage spikes on broadcast-heavy WebSocket endpoints because each outgoing message is serialized separately per subscriber instead of once per broadcast.
triggers: ["CPU pegged when broadcasting to a room", "broadcast gets slower as more people join a channel", "JSON.stringify is a hotspot in the profiler", "large rooms cause latency spikes for everyone", "fan-out CPU scales with subscriber count"]
permissions: ["READ"]
---

## Symptom
A broadcast-style endpoint (a chat room, a live sports/ticker feed, a
collaborative document) performs fine with a handful of subscribers
per channel but CPU usage and broadcast latency both climb sharply as
individual rooms/channels grow to hundreds or thousands of
subscribers -- and profiling during a broadcast shows a large fraction
of time in serialization (`JSON.stringify` or equivalent) rather than
in actual network I/O, with the cost scaling visibly with subscriber
count for a single logical message rather than staying constant.

## Likely causes
1. **The broadcast loop serializes the message independently inside
   the per-subscriber send call** -- a pattern like `subscribers.forEach(s
   => s.send(JSON.stringify(message)))` re-runs full serialization once
   per subscriber for what is logically one message, turning an O(1)
   serialization cost into an O(subscribers) cost that dominates as
   room size grows.
2. **Per-subscriber message customization is done more broadly than it
   needs to be** -- if only a small piece of the payload actually
   differs per recipient (a per-user unread flag, a redacted field for
   permission reasons) but the entire message object is rebuilt and
   reserialized per subscriber instead of serializing the shared
   portion once and merging in the small per-recipient delta.
3. **Compression is applied per-message-per-connection instead of
   reusing a precompressed frame**, so a broadcast to N subscribers
   using per-message deflate does N independent compression passes
   over the same bytes instead of compressing once and reusing the
   compressed frame across sends where the compression context allows
   it.
4. **The broadcast path holds a lock or iterates a shared subscriber
   list synchronously across the whole serialize-and-send sequence**,
   so even if serialization itself were cheap, the broadcast as a
   whole still blocks the event loop or a worker thread for a duration
   proportional to subscriber count, delaying delivery to everyone
   including subscribers that could have received their copy
   immediately.

## Diagnose
- Profile CPU during a broadcast to a large room specifically (CPU
  profiler, flamegraph, or simple wall-clock timing around the
  broadcast function) and check what fraction of time is in
  serialization versus actual socket writes -- a serialization-
  dominated profile that scales with subscriber count confirms this
  pattern rather than a network-bound issue.
- Grep the broadcast/fan-out code for where `JSON.stringify` (or the
  language's equivalent) is called relative to the per-subscriber loop
  -- inside the loop is the direct signature; outside and reused
  across the loop is correct.
- Measure broadcast latency (time from "message ready to send" to
  "last subscriber's send call returns") for rooms of varying size,
  holding message size constant -- latency growing roughly linearly
  with subscriber count for a fixed message size points at per-
  subscriber serialization cost rather than genuine per-connection
  network variance.
- Check whether per-message compression (`permessage-deflate`) is
  enabled and, if so, whether the library/configuration allows sharing
  a compression context or precompressed buffer across sends of
  identical content to multiple connections, versus compressing fresh
  for each.
- Check whether the broadcast loop is synchronous/blocking for its
  full duration by measuring event-loop lag (or the runtime's
  equivalent) during a large-room broadcast -- lag spikes correlated
  with broadcast events confirm the loop is blocking other work.

## Fix
Do the work that's shared across subscribers exactly once per
broadcast, and only repeat the work that's genuinely per-subscriber:
- Serialize the message once outside the per-subscriber loop and send
  the same resulting buffer/string to every subscriber that needs the
  identical payload -- reserve per-subscriber serialization only for
  the actual per-recipient delta, applied as a smaller merge step
  rather than a full re-serialize.
- Where compression is enabled, prefer sending the same precompressed
  frame to multiple connections when the library supports a shared
  compression context, or benchmark whether disabling per-message
  compression for very large broadcast rooms nets a better latency/CPU
  trade-off than paying per-connection compression cost on every
  broadcast.
- Batch the send loop asynchronously (yield back to the event loop
  periodically, or parallelize sends across a worker pool) rather than
  completing the entire subscriber list synchronously, so a broadcast
  to a very large room doesn't monopolize the thread that also needs
  to handle other connections' traffic.
- For very large rooms, consider whether every subscriber truly needs
  individual delivery at all versus a CDN/edge-level fan-out mechanism
  designed for one-to-many delivery at scale (relevant once room size
  reaches into the tens of thousands), rather than scaling the
  application server's own broadcast loop indefinitely.

## Pitfalls
- Caching the serialized buffer without accounting for per-recipient
  differences (permission-based redaction, per-user fields) can leak
  data meant for one subscriber to another -- confirm exactly which
  fields are genuinely shared before sharing the serialized form, and
  keep any redaction as an explicit separate step.
- Precomputing and caching a serialized message for reuse across
  multiple broadcasts (not just fanning it out once) can serve stale
  data if the message or a piece of shared state changes between
  intended broadcasts -- scope any caching to a single broadcast
  event, not a longer-lived cache.
- Parallelizing sends across a worker pool without bounding
  concurrency can create its own resource spike (too many simultaneous
  writes contending for network buffers) -- bound worker/batch
  concurrency rather than firing all sends fully in parallel with no
  limit.

## Verify
Benchmark broadcast latency and CPU usage for a fixed message size
across a range of room sizes (e.g. 10, 1,000, 50,000 subscribers) and
confirm serialization cost stays roughly constant per broadcast
regardless of subscriber count (visible as broadcast latency growing
sub-linearly, dominated by actual per-connection I/O rather than
repeated serialization), and that event-loop lag during a large-room
broadcast stays within the same bounds as during normal, non-broadcast
traffic.
