---
name: mysql-online-schema-change-replica-semaphore-deadlock
description: A large online schema change or table rename on the primary causes read replicas to hang with InnoDB semaphore waits and then crash-recover.
triggers: ["replica crashed after schema migration", "innodb semaphore wait too long", "gh-ost migration killed replicas", "replica restarted itself during migration", "pt-online-schema-change replica lag spike"]
permissions: ["READ"]
---

## Symptom
Shortly after (or during) a large online schema-change operation on the
primary -- an `ALTER TABLE`, a `RENAME TABLE` swap from a tool like
gh-ost or pt-online-schema-change, or a bulk backfill -- one or more read
replicas stop responding to queries, log
`InnoDB: a long semaphore wait`, and then crash and go through InnoDB
crash recovery. Once the first replica restarts, remaining replicas take
a disproportionate share of read traffic and sometimes fail in turn,
because the fleet had no slack for one member disappearing.

## Likely causes
1. **The schema-change tool's final cutover (a metadata lock plus atomic
   `RENAME TABLE`) coincides with the replica replaying a large burst of
   row-based binlog events against the same table**, and the replica's
   single SQL thread has to hold buffer pool pages and metadata locks
   long enough that a background thread (purge, or another query) waits
   past InnoDB's internal semaphore timeout, which is treated as fatal.
2. **The replica's buffer pool is too small relative to the working set
   touched by the migration**, so replaying millions of row events causes
   heavy random I/O and page eviction, and semaphore waits stack up under
   I/O pressure that the primary itself doesn't experience the same way
   (the primary has different query plans/indexes in flight).
3. **No throttling on the schema-change tool relative to replica
   lag/load** -- tools like gh-ost and pt-online-schema-change have
   built-in throttling controls, but if they're run with defaults or with
   throttling disabled "to finish faster," they can push copy/apply
   traffic faster than replicas can safely absorb.
4. **Losing one replica removes capacity headroom the rest of the fleet
   was implicitly depending on** -- the initial crash is a symptom of the
   migration; the cascading failure of remaining replicas is a separate,
   compounding problem of running the fleet too close to saturation, so
   the remaining replicas were never sized to absorb one member's traffic
   share plus their own.

## Diagnose
- Check the crashed replica's error log around the crash timestamp for
  `InnoDB: a long semaphore wait` and the specific thread/mutex it names
  -- this confirms an internal wait, not an OOM kill or disk-full event.
- Correlate the crash timestamp against the schema-change tool's own
  log (gh-ost/pt-osc print progress and cutover timing) to confirm the
  crash lines up with the cutover step or a period of high copy-throughput,
  not an unrelated event.
- Check replica `SHOW REPLICA STATUS` (or `SHOW SLAVE STATUS` on older
  versions) history/monitoring for `Seconds_Behind_Source` climbing in
  the minutes before the crash, indicating the SQL thread was already
  falling behind before it failed outright.
- Compare replica buffer pool size (`innodb_buffer_pool_size`) and disk
  I/O metrics against the primary's -- replicas are frequently
  under-provisioned relative to the primary on the assumption that reads
  are "just serving traffic," which breaks down during a heavy write
  replay.
- Check whether the schema-change tool was run with throttling flags
  (`--max-lag`, `--throttle-control-replicas` for gh-ost;
  `--max-lag`, `--critical-load` for pt-osc) pointed at the actual
  replica fleet, or left at permissive defaults.

## Fix
- Run large schema-change/backfill operations with explicit
  replica-lag-aware throttling configured against the real replica set
  (not just the primary), so the tool slows or pauses copy/apply
  throughput automatically when a replica falls behind, rather than
  assuming the primary's health is a sufficient proxy for the fleet's.
- Schedule the cutover step for a low-traffic window and, where
  supported, stage it so metadata-lock duration on the rename is minimal
  -- the copy/backfill phase can run for hours safely, but the atomic
  rename should be as short as possible since it's the step most likely
  to compound with replica replay pressure.
- Size replica buffer pool and I/O capacity to handle write-replay bursts,
  not just steady-state read-query load, since a schema change is
  effectively a large write burst the replica must apply serially.
- Build fleet headroom into replica capacity planning explicitly: the
  fleet should tolerate losing one replica (to a crash, a restart, or
  planned maintenance) without the remaining replicas saturating, which
  means routine capacity planning needs an "N-1" check, not just
  peak-traffic sizing.

## Pitfalls
- Treating the crash as purely a "replica hardware" problem and just
  restarting it without addressing the throttling gap means the next
  large migration reproduces the same cascading failure.
- Disabling a schema-change tool's throttling "to make the migration
  finish before the maintenance window closes" trades a scheduling
  inconvenience for a production incident risk -- if the window is too
  short for a safely-throttled run, the right fix is a longer window or
  a smaller batch, not disabling the safety mechanism.
- Load-balancer/proxy health checks that pull a crashed replica out of
  rotation are necessary but not sufficient -- if remaining replicas
  weren't sized for N-1, removing the unhealthy one accelerates the
  cascade rather than preventing it.

## Verify
Re-run the same class of schema-change operation (or a realistic
rehearsal on a staging replica set sized like production) with
throttling enabled and buffer pool sized per the fix, and confirm via
`SHOW REPLICA STATUS` and the error log that `Seconds_Behind_Source`
stays bounded throughout the run and no semaphore-wait crash occurs;
separately, confirm via a load test that removing one replica from the
pool mid-traffic does not push the remaining replicas past a safe
utilization threshold.
