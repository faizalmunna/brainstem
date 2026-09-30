---
name: mysql-failover-replication-lag-data-gap
description: A newly promoted MySQL primary after a cross-region failover is missing the last few seconds of writes and the application has no way to detect the gap.
triggers: ["missing writes after failover", "data disappeared after database failover", "newly promoted primary missing recent rows", "replication lag caused data loss on failover", "cross region failover lost transactions"]
permissions: ["READ"]
---

## Symptom
After an automated or manual failover -- often triggered by a network
partition or a primary becoming unreachable during maintenance -- the
newly promoted primary is missing writes that clients had already
received success acknowledgments for seconds before the failover. Users
report data "disappearing" (an order, a comment, a status update that
was confirmed as saved), and there's no error anywhere in application
logs, because from the application's perspective those writes simply
succeeded and were never seen again. This is especially likely when the
old primary and its replicas are geographically distant (cross-region or
cross-continent), where network latency alone means replication lag is
routinely several seconds, not milliseconds.

## Likely causes
1. **Asynchronous replication was in use, and the promoted replica was
   behind the old primary at the moment of failover** -- by design,
   asynchronous replication acknowledges a write as committed on the
   primary before confirming it has been applied anywhere else, so any
   write not yet shipped and applied to the promoted replica at failover
   time is simply gone from the new primary's perspective, with no error
   raised to the client that made the write.
2. **Replication lag was elevated specifically because of long network
   distance** between the primary and the replica that got promoted --
   cross-region/cross-continent replication topologies have materially
   higher baseline lag than same-datacenter replication, and a failover
   during or shortly after a network partition (which is often exactly
   when lag spikes further) maximizes the window of at-risk writes.
3. **The failover was triggered by the same network event that was also
   delaying replication**, meaning the moment of highest lag (and
   therefore highest data-loss risk) coincides with the moment failover
   automation decided to act, rather than these being independent events.
4. **No semi-synchronous replication or write-durability guarantee was
   configured** for the specific data that mattered (semi-sync
   replication would have made the primary wait for at least one replica
   acknowledgment before confirming the write, closing most of this gap
   at a latency cost) -- async was chosen for latency reasons without an
   explicit tradeoff decision documented for what happens on failover.
5. **The application has no idempotency key or write-receipt reconciliation
   mechanism**, so even if the gap is detected at the database level,
   there's no way to identify which specific client-visible transactions
   were affected and replay or surface them.

## Diagnose
- Compare the old primary's last-known GTID position or binlog
  position/offset (from its error log, monitoring snapshot, or any
  surviving copy of its binlogs) against the promoted replica's
  applied position at the moment of promotion -- the difference
  identifies the exact set of transactions that were committed on the
  old primary but never replicated.
- Check replication lag monitoring (`Seconds_Behind_Source` /
  `Seconds_Behind_Master` history, or GTID-gap monitoring) for the
  period immediately before the failover to quantify how far behind the
  promoted replica actually was, and whether lag was already elevated
  before the triggering event or spiked because of it.
- Determine the replication mode in use at failover time
  (`SHOW VARIABLES LIKE 'rpl_semi_sync%'`, or the topology's documented
  configuration) -- confirm whether this was asynchronous or
  semi-synchronous replication, since the loss mechanism and the
  available mitigations differ.
- If the old primary's data directory or binlogs are still recoverable
  (not always true after a full regional outage), extract the
  transactions present in its binlogs after the promoted replica's last
  applied position -- this is the authoritative list of at-risk/lost
  writes, useful for both scoping the incident and for possible manual
  reconciliation.
- Check whether the application logged write acknowledgments
  independently of the database (e.g., an application-level audit log or
  message queue) that could be cross-referenced against what actually
  landed on the new primary, since the database alone won't show you
  what's missing without an external reference point.

## Fix
- For data where write loss on failover is unacceptable, configure
  semi-synchronous replication (or a quorum-based commit mechanism, on
  systems that support it) for at least one replica in the failover
  candidate set, so a write isn't acknowledged to the client until it's
  durable on more than just the primary -- this trades some write
  latency for closing the async replication gap.
- Explicitly decide and document, per data class, whether asynchronous
  replication's failover data-loss window is acceptable -- some data
  (ephemeral caches, low-stakes logs) may genuinely be fine with async
  and its latency benefit; other data (financial transactions, order
  state) usually is not, and that should be a deliberate choice, not a
  default inherited from initial setup.
- Prefer promoting the least-lagged replica specifically (not just "a"
  healthy replica) when failover automation has a choice among multiple
  candidates, and factor real-time lag into the promotion decision rather
  than treating all in-sync-enough replicas as equivalent.
- Build a reconciliation path for the data class that can't fully avoid
  the gap: an idempotency key or client-side write receipt that lets the
  application detect "I was told this succeeded but it's not present"
  after a failover and either replay from a durable source (a message
  queue, an application-level log) or surface the discrepancy for manual
  handling, rather than silently losing it with no trace.

## Pitfalls
- Assuming semi-sync replication alone eliminates the gap entirely --
  semi-sync with a short timeout that falls back to async under network
  stress (a common default) can silently degrade to async exactly during
  the network partition scenario that also triggers failover, reopening
  the same gap at the worst possible moment.
- Treating this as solved by "faster failover detection" alone --
  reducing detection time shrinks the window but doesn't address the
  fundamental async-replication acknowledgment gap; a fast failover to a
  lagged replica still loses the same in-flight writes.
- Adding semi-sync replication cluster-wide without capacity-testing the
  added write latency, especially across the same long network paths
  that caused the lag problem in the first place -- semi-sync makes
  every write wait on a round trip to a replica, which is expensive
  precisely in the cross-region topologies where this failure mode is
  most likely.

## Verify
In a staging environment with a comparable cross-region topology,
simulate a network partition to the primary and force a failover under
active write load, then compare the write log the application/client
believed succeeded against what's present on the promoted primary;
confirm that either (a) the gap is zero because semi-sync/quorum commit
is correctly enforced and doesn't silently fall back to async under the
simulated partition, or (b) the reconciliation mechanism correctly
identifies and surfaces every write that didn't make it across.
