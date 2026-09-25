---
name: mysql-single-threaded-replication-lag
description: A read replica falls further and further behind the primary even though the primary has plenty of spare write capacity and no CPU or I/O pressure.
triggers: ["replica lag keeps growing", "seconds behind master increasing", "replication lag despite low primary load", "replica cant keep up with primary", "sql thread falling behind"]
permissions: ["READ"]
---

## Symptom
`Seconds_Behind_Source` (or `Seconds_Behind_Master`) on a read replica
climbs steadily, sometimes to minutes or hours, even though the primary
itself shows low CPU, low I/O wait, and clearly has headroom to accept
more writes. Reads served from the lagging replica return stale data,
and the lag doesn't recover even during quieter traffic periods,
suggesting the replica is structurally unable to keep pace rather than
just temporarily behind.

## Likely causes
1. **The replication SQL thread applies transactions from a single
   primary in commit order on a single thread (in the classic,
   non-parallel replication configuration)**, so even if the primary
   accepted many writes concurrently across many connections, the
   replica must replay them serially -- a primary with high write
   *concurrency* but only moderate total throughput can still overwhelm
   a single-threaded replica apply path that has no equivalent
   parallelism.
2. **Multi-threaded (parallel) replication isn't enabled, or is enabled
   but configured with a parallelism mode that doesn't fit the workload**
   -- `slave_parallel_workers`/`replica_parallel_workers` at 0 or 1 means
   no parallel apply at all; even when enabled, the default
   `DATABASE`-based parallelization only parallelizes across different
   schemas, which does nothing for a workload concentrated in one
   database.
3. **A small number of hot rows/tables serialize replica apply even with
   parallel replication enabled** -- `LOGICAL_CLOCK`-based parallelism
   still respects true dependencies between transactions, so a workload
   with frequent contention on the same rows on the primary produces
   inherently sequential dependencies the replica can't parallelize away
   regardless of configuration.
4. **The replica itself has weaker I/O or is running additional load**
   (backups, analytical queries, a second role) competing with the
   replication apply thread for the same disk/CPU resources, meaning the
   bottleneck is on the replica side even though the primary looks idle.
5. **A large, slow-to-apply statement replicated as one unit** -- a bulk
   `UPDATE`/`DELETE` affecting many rows, or a statement-based-replication
   event that's expensive to re-execute, can occupy the SQL thread for
   an extended single stretch, during which lag accumulates from every
   subsequent primary write queued behind it.

## Diagnose
- Check `SHOW REPLICA STATUS` (`SHOW SLAVE STATUS` on older versions)
  for `Seconds_Behind_Source` trend over time (not just a point-in-time
  read) and check whether `Replica_SQL_Running_State` shows the thread
  actively applying versus waiting.
- Check `slave_parallel_workers` / `replica_parallel_workers` and
  `slave_parallel_type` / `replica_parallel_type` -- confirm whether
  parallel replication is enabled at all, and if so, whether it's using
  `DATABASE` (parallelizes by schema) or `LOGICAL_CLOCK`
  (parallelizes based on the primary's actual commit dependency
  tracking, generally more effective for a single-schema workload).
- On the replica, check CPU/disk I/O utilization specifically for the
  replication applier threads (not just overall host metrics) --
  distinguish "the replica's apply thread(s) are saturated" from "the
  replica host has other competing load."
- On the primary, check `SHOW BINLOG EVENTS` or binlog size/rate around
  the lag window for any single very large transaction or bulk statement
  that could occupy the SQL thread for an extended stretch.
- Check for lock contention or long-running transactions specifically on
  the replica (`SHOW PROCESSLIST`, `SHOW ENGINE INNODB STATUS`) that
  might be blocking the SQL thread's own writes, separate from primary-side
  activity entirely.

## Fix
- Enable multi-threaded replication with `LOGICAL_CLOCK`-based
  parallelism (`slave_parallel_type=LOGICAL_CLOCK`,
  `slave_parallel_workers` set to a reasonable multiple of available
  replica cores) so independent transactions from the primary can apply
  concurrently on the replica instead of serially, which directly
  addresses the concurrency-mismatch root cause.
- For workloads still bottlenecked by true row-level contention even
  with parallel replication enabled, look for ways to reduce contention
  at the source (batching writes to hot rows differently, spreading load
  across more distinct rows) since no replication configuration can
  parallelize genuinely dependent transactions.
- If the replica's own hardware/I/O is the bottleneck, address that
  directly (faster storage, dedicated replica not sharing load with
  backup/analytical jobs) rather than assuming replication configuration
  alone can compensate for genuinely under-provisioned replica hardware.
- For large bulk operations, break them into smaller batches on the
  primary (chunked `UPDATE`/`DELETE` with a bounded row count per
  statement/transaction) so no single replicated transaction occupies
  the SQL thread long enough to create a large lag spike, independent of
  parallel-replication configuration.

## Pitfalls
- Enabling parallel replication without giving the replica enough spare
  CPU cores to actually run multiple apply workers concurrently just
  moves the bottleneck from "single thread, low CPU" to "many threads,
  contended CPU" without improving effective throughput.
- Assuming parallel replication alone fully solves lag for a
  hot-row-contended workload -- transactions with true dependencies are
  still serialized correctly (this is required for correctness), so lag
  from genuine contention needs an application-level fix, not just a
  replication configuration change.
- Treating replica lag purely as a replication-configuration problem
  without checking the replica's own competing workload (reporting
  queries, backups scheduled against the same instance) -- a "fix" to
  replication settings won't help if the real constraint is the replica
  host being busy with unrelated work.

## Verify
After enabling/tuning parallel replication, monitor
`Seconds_Behind_Source` under realistic peak write concurrency (not just
peak write volume) and confirm it stays bounded and recovers promptly
after any transient spike; separately confirm via
`SHOW REPLICA STATUS` and worker-thread-level metrics that multiple
parallel apply workers are actually active concurrently during the
peak window, not just configured but idle.
