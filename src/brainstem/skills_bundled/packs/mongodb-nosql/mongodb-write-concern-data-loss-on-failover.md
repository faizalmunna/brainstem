---
name: mongodb-write-concern-data-loss-on-failover
description: Diagnose data that appeared to be durably written to MongoDB disappearing after a primary failover due to a weaker-than-assumed write concern.
triggers: ["data disappeared after mongodb failover", "write succeeded but data is gone", "lost writes after primary election", "acknowledged write not persisted after failover", "data loss after replica set election"]
permissions: ["READ"]
---

## Symptom
A write operation returns success to the application, but after a
replica set primary failover (planned maintenance, a crash, or a network
partition triggering an election), some recently-written data is simply
gone -- not corrupted, not partially written, just absent, as if the
write never happened. This is confusing specifically because the driver
reported acknowledgment, so the application logic assumed durability.

## Likely causes
1. **Write concern set to `w: 1` (or the driver/server default, which
   historically was `w: 1` in some configurations)** acknowledges a
   write as soon as the primary applies it, before any secondary has
   replicated it -- if the primary fails and a secondary that hadn't yet
   replicated that write is elected, the write is lost from the new
   primary's perspective, and once the old primary rejoins, its
   divergent data is rolled back to match the new primary.
2. **`journal: false` (or an older MongoDB version with weaker default
   journaling behavior) combined with a crash** -- a write acknowledged
   before being written to the journal can be lost if the process
   crashes (not just fails over) before the journal flush, independent
   of replication.
3. **Application code assumes "acknowledged" means "durable across
   failover"** -- these are different guarantees; `w: 1` durability is
   local-disk durability on the primary, not cluster-wide durability,
   and the distinction only becomes visible during an actual failover
   event, which may be rare enough that the gap goes unnoticed for a
   long time.
4. **A mixed write concern across the codebase** -- some write paths
   correctly use `w: "majority"` for critical data, but a newer feature
   or a bulk-import script defaults to the driver's out-of-the-box
   setting without anyone deciding that was acceptable for that data.
5. **Replication lag at the moment of failover** -- even with a
   nominally correct write concern configuration elsewhere, a
   secondary that's significantly lagged when a failover happens can
   still be elected under certain election-timing edge cases, especially
   if `getLastErrorDefaults`/replica set settings don't prioritize
   up-to-date members appropriately.

## Diagnose
- Check the write concern actually used on the affected write path in
  code (not just what's documented/assumed) -- look for the specific
  `writeConcern` option passed per-operation, per-collection default, or
  the client/connection-string-level default (`w=majority` vs. no
  setting, which may default to `w:1` depending on driver/server
  version).
- Check replica set oplog window and replication lag
  (`rs.printSecondaryReplicationInfo()` or
  `db.getReplicationInfo()`) around the time of the failover to see
  whether secondaries were meaningfully behind the primary when the
  election happened.
- Review the server/replica set logs around the failover timestamp for
  rollback messages -- MongoDB logs when a former primary's divergent
  writes are rolled back after rejoining as a secondary, and the
  rollback files (or rollback directory, depending on version) record
  exactly which documents were affected.
- Confirm journaling configuration (`storage.journal.enabled`) and
  whether any custom write concern disabled it for performance reasons
  without an explicit durability tradeoff decision being documented.

## Fix
- Use `w: "majority"` for any write where losing it on failover is
  unacceptable -- this requires the write to be acknowledged by a
  majority of voting replica set members before returning success,
  which guarantees it survives any single-primary failover since a
  newly elected primary must also have that majority-acknowledged data.
- Pair `w: "majority"` with an appropriate read concern (`"majority"`)
  for reads that must reflect only durably-committed data, if the
  application also needs to avoid reading data that could later be
  rolled back.
- Audit write concern settings across all write paths explicitly, per
  collection/operation type, rather than relying on a single global
  default -- some genuinely latency-sensitive, non-critical writes (e.g.
  ephemeral analytics counters) may reasonably use a weaker write
  concern; the point is that it's a deliberate choice, not an accident.
- Set appropriate `wtimeout` alongside `w: "majority"` so writes fail
  fast and visibly (allowing the application to retry or alert) if
  majority acknowledgment can't be achieved, rather than hanging
  indefinitely during a genuine cluster problem.

## Pitfalls
- Setting `w: "majority"` everywhere without considering latency impact
  -- majority writes wait for replication round-trip, which is slower
  than `w: 1`; apply it deliberately to data that needs the guarantee,
  not reflexively to every write in the system, or unrelated
  performance-sensitive paths regress.
- Assuming `w: "majority"` alone protects against every loss scenario --
  it protects against failover-related rollback of acknowledged writes,
  but doesn't substitute for proper journaling/disk durability
  configuration or protect against application-level bugs like retrying
  a write that already partially succeeded.
- Fixing write concern going forward without acknowledging that already-
  lost data during a past incident needs separate recovery (from
  backups, from upstream source-of-truth systems, or accepting the
  loss) -- the write concern fix prevents recurrence, it doesn't
  retroactively recover what's already gone.

## Verify
In a staging replica set, run a write with the corrected write concern,
then force a primary step-down (`rs.stepDown()`) immediately after and
confirm the write is present and consistent on the newly elected
primary; also confirm the driver surfaces a clear error/timeout (rather
than silent success) when majority acknowledgment genuinely cannot be
achieved (e.g. with insufficient healthy voting members in a test
scenario).
