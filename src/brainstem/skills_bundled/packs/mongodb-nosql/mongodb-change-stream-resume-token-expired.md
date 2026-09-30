---
name: mongodb-change-stream-resume-token-expired
description: Diagnose a change stream consumer that falls behind, loses its resume token, and requires an unplanned full resync instead of a clean restart.
triggers: ["change stream resume token invalid", "change stream cannot resume", "changestreamhistorylost error", "change stream consumer needs full resync", "change stream fell behind and cant catch up"]
permissions: ["READ"]
---

## Symptom
A service consuming a MongoDB change stream (for cache invalidation,
search index sync, downstream event publishing, or CDC-style
replication) stops and, on restart, fails to resume with an error
referencing an invalid or expired resume token (e.g.
`ChangeStreamHistoryLost`), meaning it can no longer pick up where it
left off -- the only path forward is either accepting a gap in events or
doing a full resync of the destination from the source collection,
which for a large collection can take hours and requires careful
coordination to avoid serving stale data during the rebuild.

## Likely causes
1. **The consumer was down (crashed, deployed, or throttled) for longer
   than the oplog/change stream retention window**, so by the time it
   tries to resume from its last saved token, the oplog entries needed
   to replay from that point have already been overwritten -- the oplog
   is a capped, finite-retention structure, not unbounded history.
2. **The consumer fell behind processing-wise (not down, just slow)**
   under load, and the gap between "oldest unprocessed event" and
   "current oplog head" grew past the retention window before the
   consumer could catch up -- a slow consumer eventually hits the same
   wall as a stopped one.
3. **The resume token wasn't persisted durably/frequently enough** -- if
   tokens are only checkpointed occasionally (e.g. every N events or
   every few minutes) rather than after each processed batch, a crash
   between checkpoints loses more progress than necessary, and if that
   gap plus time-to-restart exceeds retention, resumption fails even
   though a more recent token would have still been valid.
3. **Oplog size/retention was sized for normal operational restarts, not
   for the realistic worst-case consumer downtime** (a multi-hour
   incident, a batch job that pauses consumption, a deploy that takes
   longer than expected) -- retention window and expected downtime
   were never explicitly reconciled against each other.
4. **A collection or database-level change (e.g. a collection drop/
   rename, or dropping and recreating the collection being watched)
   invalidates the change stream independent of timing** -- this looks
   similar (stream can't resume) but has a structural cause rather than
   a retention-window cause.

## Diagnose
- Check the exact error code/message from the failed resume attempt --
  `ChangeStreamHistoryLost` specifically indicates the resume token's
  position is no longer in the oplog, as distinct from other
  resumption errors caused by a collection-level DDL change.
- Check how long the consumer was actually down or behind before this
  restart attempt (from consumer logs/monitoring or the last successfully
  processed event's timestamp) and compare that against the oplog
  window (`db.getReplicationInfo()` reports the oplog's time range) at
  the time of the incident.
- Check how frequently resume tokens were checkpointed/persisted in the
  consumer's own logic -- if checkpointing was infrequent, the effective
  "lost progress" on restart is larger than the actual downtime alone
  would suggest.
- If using MongoDB's `changeStreamPreAndPostImages` or a dedicated
  change stream retention setting (available in newer server versions),
  check whether that was configured with a retention window that
  matches realistic consumer downtime scenarios, not just the default.

## Fix
- Increase oplog size (or the dedicated change stream pre/post-image
  retention setting on newer versions) to comfortably exceed the
  realistic worst-case consumer downtime, not just typical restart
  time -- size for incident scenarios (a multi-hour outage, a slow
  deploy), not the happy path.
- Checkpoint the resume token frequently and durably (after every
  processed batch, not on a coarse timer), so that if the consumer does
  crash, the amount of progress lost -- and thus the risk of exceeding
  the retention window on resume -- is minimized.
- Build an explicit, tested fallback path for the "resume token expired"
  case: rather than treating it as an unhandled crash, catch
  `ChangeStreamHistoryLost` specifically and trigger a controlled
  resync procedure (snapshot current collection state, establish a new
  change stream from "now," reconcile) instead of discovering the need
  for a manual resync during an incident.
- Monitor consumer lag (how far behind the current oplog head the
  consumer's last processed event is) as a leading indicator, and alert
  well before that lag approaches the retention window, so a falling-
  behind consumer gets attention before it becomes an unresumable one.

## Pitfalls
- Simply increasing oplog size without also fixing checkpoint frequency
  or lag monitoring buys time but doesn't address the underlying pattern
  -- a consumer that reliably falls behind will eventually exceed
  whatever retention window is set, just less often.
- Building the resync fallback but never testing it until it's actually
  needed during a live incident -- a resync procedure that reads the
  entire source collection while production traffic continues needs its
  own care (batching, avoiding overwhelming the source, handling writes
  that happen during the resync window) that's easy to get wrong under
  pressure.
- Treating every resumption failure as "must fully resync" without first
  checking whether it's actually a `ChangeStreamHistoryLost` (retention)
  case versus a structural one (collection dropped/renamed) -- the two
  require different recovery procedures, and misdiagnosing wastes time
  during an incident.

## Verify
In a test environment, deliberately stop a change stream consumer for
longer than the configured retention window, confirm the consumer
correctly detects `ChangeStreamHistoryLost` on restart and triggers the
resync fallback rather than crash-looping or silently missing events,
and confirm the lag-monitoring alert fires well before retention
exhaustion in a slow-consumer simulation.
