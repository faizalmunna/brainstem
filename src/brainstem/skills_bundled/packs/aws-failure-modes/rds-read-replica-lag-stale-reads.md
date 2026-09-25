---
name: rds-read-replica-lag-stale-reads
description: An RDS read replica falls behind the primary under write-heavy load, serving stale data to an application that assumed near-real-time replication.
triggers: ["rds read replica lag", "read replica returning old data", "replicalag metric high", "stale reads after write rds", "read after write inconsistency rds replica"]
permissions: ["READ"]
---

## Symptom
An application that writes to the RDS primary and reads from a read
replica (for read scaling) intermittently returns data that doesn't
reflect a recent write -- a user updates a record and then, on the very
next page load routed to a replica, sees the old value -- and the
frequency of this gets worse specifically during periods of high write
volume, even though the same read path works fine during quieter periods.

## Likely causes
1. **Replication lag genuinely increases under write-heavy load** because
   RDS (and most database engines') replication is asynchronous by
   default: the replica applies the primary's write-ahead log/binlog
   sequentially, and if writes arrive faster than the replica can apply
   them (especially on a smaller/cheaper replica instance class than the
   primary), the backlog grows and visible lag increases proportionally
   with sustained write throughput.
2. **A single long-running query or lock contention on the replica
   itself blocks replication apply threads** -- a large analytical query
   or an unindexed scan running directly against the replica can hold
   locks or consume I/O that delays the replica catching up, independent
   of primary-side write volume.
3. **The application has no read-your-own-writes routing logic** -- it
   naively load-balances all reads across replicas (or a
   reader endpoint) without ever considering that a request immediately
   following its own write needs the primary (or a replica confirmed
   caught up), so the *application's assumption* of near-real-time
   replication -- not the database's actual behavior -- is the real design
   gap.
4. **The replica instance class is undersized relative to the primary**,
   so it has less I/O/CPU headroom to keep pace with the same write
   volume the primary handles comfortably, making lag an ongoing
   capacity mismatch rather than an occasional spike.
5. **Multi-AZ failover or a replica reboot recently occurred**, and the
   replica is still catching up from a cold restart of its replication
   stream, producing a temporary but potentially large lag spike that
   looks like an application bug if not correlated against RDS events.

## Diagnose
- Check the `ReplicaLag` CloudWatch metric (seconds) for the specific
  replica over the time window of reported staleness, and correlate
  against the primary's `WriteIOPS`/`WriteThroughput` metrics for the
  same window -- a clear positive correlation confirms write-volume-
  driven lag (cause 1) directly.
- Check for long-running queries on the replica specifically
  (`SHOW PROCESSLIST` / `pg_stat_activity` run against the *replica*
  endpoint, not the primary) during periods of elevated lag, to rule in/
  out cause 2.
- Review the replica's instance class against the primary's, and check
  the replica's own CPU/IOPS utilization metrics for sustained high
  utilization correlating with lag spikes (cause 4).
- Check RDS events (`aws rds describe-events`) for any recent failover,
  reboot, or replica-creation event that could explain a specific lag
  spike as a recovery/catch-up artifact rather than an ongoing steady-
  state problem.
- Audit the application's read routing logic directly: does any code
  path read from a replica immediately after a write in the same logical
  user operation, with no mechanism to either wait, route to the
  primary, or check replica freshness first?

## Fix
For genuine write-driven lag, size the replica instance class to have
real headroom over the primary's sustained write rate (not just matching
CPU/memory nominally, since replication apply is often more I/O-bound
than the primary's own write path), and consider whether write volume
itself should be reduced/batched at the source. For the application-
design gap, implement explicit read-your-own-writes handling for any
operation where a user's own recent write must be immediately visible:
route the specific follow-up read to the primary, or check replica lag
before trusting it for that read, or have the write path return the
authoritative post-write state directly to the caller instead of
requiring a re-read at all. For replica-side query contention, move
long-running analytical/reporting queries to a dedicated replica
provisioned specifically for that purpose (separate from the one serving
latency-sensitive application reads), so heavy read queries don't compete
with replication apply on the same instance. Consider RDS/Aurora's
native mechanisms where applicable (Aurora Global Database's managed
lag characteristics, or an Aurora reader's ability to be queried for its
own lag) to make replication state observable to the application layer
rather than assumed.

## Pitfalls
Solving this by always reading from the primary defeats the purpose of
having read replicas at all and can overload the primary under the same
write-heavy conditions that caused replica lag in the first place --
reserve primary reads specifically for the read-your-own-writes cases
that need them, not as a blanket routing change. Also, treating replica
lag purely as a capacity problem (bigger instance) without checking for
a specific blocking query on the replica can mean paying for a larger
instance that still lags whenever that same problematic query runs.

## Verify
After the fix, monitor `ReplicaLag` through a subsequent write-heavy
period comparable to the one that originally caused stale reads, and
confirm it stays within an acceptable bound (define this explicitly,
e.g., under N seconds, rather than just "lower than before"). For the
read-your-own-writes fix specifically, write an end-to-end test that
performs a write followed immediately by the exact read path a user
would hit, and confirm it reflects the write every time, including
during a synthetic write-heavy load test run concurrently.
