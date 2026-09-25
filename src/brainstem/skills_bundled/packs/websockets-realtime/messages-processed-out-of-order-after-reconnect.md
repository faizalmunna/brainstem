---
name: messages-processed-out-of-order-after-reconnect
description: A client processes real-time messages out of order relative to before a disconnect because message ordering isn't preserved or reconciled across a WebSocket reconnection.
triggers: ["messages arrive out of order after reconnect", "state gets corrupted after a dropped connection", "duplicate or missing updates after reconnect", "client shows stale data after reconnecting", "race condition between reconnect and buffered messages"]
permissions: ["READ"]
---

## Symptom
After a WebSocket disconnects and reconnects (whether from a network
blip, a server restart, or the normal reconnection-storm scenario),
the client's state ends up inconsistent with the server's -- an update
that happened during the gap is skipped, an old update arrives after a
newer one and overwrites it, or the same update is applied twice. The
bug is intermittent and timing-dependent: it reproduces reliably only
when a real message happens to be in flight or queued at the exact
moment of disconnect, so it's easy to miss in testing that always
disconnects during quiet periods.

## Likely causes
1. **No sequence numbers or versioning on messages**, so the client has
   no way to detect that it missed messages during the disconnect gap,
   or that a message it just received is older than one it already
   applied -- it has to trust that whatever arrives next is the
   correct next state, which isn't a safe assumption across a
   reconnect.
2. **The client doesn't request a fresh snapshot or resync point on
   reconnect**, instead just resuming live message consumption from
   whatever the server sends next -- silently leaving a gap for
   whatever changed during the disconnected interval, with the client
   never even aware something was missed.
3. **A new connection's messages race with the old connection's
   in-flight/buffered messages** -- if the client doesn't fully tear
   down the old socket's message handling before wiring up the new
   one (e.g. an async operation still resolving from the old
   connection, or a message that was in the OS receive buffer but not
   yet processed), messages from the stale connection can be applied
   after messages from the new one, reversing their intended order.
4. **Server-side fan-out doesn't preserve per-client ordering across
   the underlying pub/sub layer** -- if messages for the same logical
   stream are published across multiple partitions/shards of the
   fan-out backend (see this pack's fan-out skill) without a
   partitioning key that keeps a given entity's updates together, two
   updates to the same resource can be delivered to a subscriber out
   of the order they were produced in, independent of any reconnect at
   all.

## Diagnose
- Check whether messages carry any sequence number, version, or
  logical timestamp the client can compare against what it already
  applied -- absence of any such field is the first sign the system
  has no way to even detect reordering, let alone correct it.
- Reproduce directly: connect a client, disconnect its network at the
  transport level (not a clean close) while the server is actively
  sending updates to the same resource, reconnect, and diff the
  client's final state against the server's authoritative state --
  divergence confirms the issue independent of root cause.
- Add logging on the client for every message's sequence number (or,
  absent one, a content hash/timestamp) as applied, and specifically
  watch the handoff moment between old and new connection after a
  reconnect for out-of-order arrival between the two sockets'
  messages.
- On the server/fan-out side, check whether messages for a single
  logical entity (a specific room, document, or record) are always
  published through the same partition/shard key, or whether they can
  be spread across shards that don't preserve relative ordering
  between them.
- Check what the client does immediately upon reconnect -- whether it
  requests a resync/snapshot with a "last seen sequence number"
  parameter, or simply starts consuming the live stream from whatever
  arrives next with no gap-filling step.

## Fix
Make ordering and gap-detection explicit rather than assumed:
- Attach a monotonically increasing sequence number (or a per-entity
  version) to every outgoing message, scoped to whatever granularity
  ordering actually matters at (per-room, per-document, per-user
  stream) -- the client compares each arriving sequence number against
  the last one it applied and can now detect both gaps and
  reordering instead of blindly trusting arrival order.
- On reconnect, have the client send the last sequence number it
  successfully applied and have the server respond with either the
  missed messages (if the gap is small and recent enough to replay) or
  a full snapshot plus the current sequence number (if the gap is too
  large to replay, e.g. after an extended disconnect) -- this closes
  the exact gap this pattern otherwise leaves silently unfilled.
- Fully tear down the old connection's message handling (unsubscribe
  its handlers, ignore/discard any message tagged as belonging to the
  superseded connection) before or atomically with wiring up the new
  connection, so there's no window where both sockets' messages can
  interleave into the application state.
- On the fan-out side, key partitioning by the entity whose ordering
  matters (route all updates for the same room/document to the same
  partition) so the underlying pub/sub or streaming layer's own
  ordering guarantees (most partitioned systems guarantee order within
  a partition) actually apply to the sequences that need it.

## Pitfalls
- Using wall-clock timestamps instead of a monotonic sequence number
  for ordering is unreliable across clients/servers with clock skew,
  and doesn't cleanly express "these two messages happened in this
  exact relative order" the way an incrementing counter does --
  reserve timestamps for display/logging, not ordering logic.
- Replaying every missed message after a long disconnect instead of
  falling back to a snapshot for large gaps can mean the client spends
  longer processing a backlog than it was ever disconnected for, and
  can re-derive intermediate states nobody needs -- cap replay to a
  reasonable gap size and snapshot beyond that.
- Deduplicating solely by "did I already see this sequence number"
  without also handling true duplicates from at-least-once delivery
  semantics in the fan-out backend can either double-apply a
  redelivered message or, if implemented carelessly, reject a
  legitimate later message that happens to reuse tracking state
  incorrectly -- test the interaction between the fan-out backend's
  delivery guarantees and the client's dedup logic explicitly.

## Verify
Simulate a disconnect with real traffic in flight (updates to the
same resource happening during the gap), reconnect, and confirm the
client's resync request includes its last-applied sequence number,
the server's response either replays exactly the missed messages in
order or provides a snapshot at a known sequence number, and the
client's final state exactly matches the server's authoritative state
with no message applied twice (checked via sequence-number gaps or
duplicates in the client's applied-message log).
