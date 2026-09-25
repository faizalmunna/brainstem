---
name: failover-primary-missing-recent-writes-from-replication-lag
description: A newly promoted database primary is missing the last several seconds of writes after an automatic failover during a network partition.
triggers: ["data missing after failover", "promoted replica missing recent writes", "failover lost transactions", "new primary out of sync after partition"]
permissions: ["READ"]
---

## Symptom

A database (or any primary/replica system with automatic failover)
experiences a network blip or maintenance event, an automatic failover
promotes a replica to primary, and afterward some writes that clients
believed were committed -- often the last few seconds to minutes before
the failover -- are simply gone. Applications report records that
"disappeared," duplicate-key errors on retried writes that should have
already existed, or downstream consumers processing an event stream
that skips a gap of IDs.

## Likely causes

- **Asynchronous replication with a lag window wider than the failover
  detection time**, especially over long-haul/cross-region links --
  the primary acknowledged the write to the client before the replica
  received it, so any replica promoted during that lag window is
  missing those writes by design, not by bug.
- **Failover automation doesn't wait for the most caught-up replica**,
  promoting whichever replica responds fastest or is configured as
  the designated failover target, even when a different replica was
  measurably more current at the moment of the partition.
- **The write acknowledgment level doesn't match the durability
  assumption the application is making** -- e.g. the driver or ORM is
  configured for a fire-and-forget or leader-only ack, but application
  code and downstream consumers behave as if every acknowledged write
  is durably replicated to whatever becomes the next primary.
- **The old primary comes back after the partition heals and briefly
  continues accepting writes** (or replaying a local queue) before
  it's fenced off, creating writes that exist only on the demoted node
  and are lost when it's finally reconciled or wiped.

## Diagnose

1. Pull the replication lag metric (e.g. `pg_stat_replication` /
   `SHOW SLAVE STATUS` seconds-behind-master / cloud provider's replica
   lag metric) for the promoted replica at the timestamp immediately
   preceding the failover -- confirm whether it was non-zero and by
   how much.
2. Compare the write-ahead log / binlog position (or sequence number)
   of the promoted replica against the last known LSN/GTID on the old
   primary before it went unreachable, to quantify exactly how many
   transactions were in flight and unreplicated.
3. Check the failover orchestrator's logs (Patroni, Orchestrator, RDS/
   Aurora failover events, MongoDB replica set election logs) for which
   replica was selected and whether it logged a "selecting most
   up-to-date replica" step or just picked a static priority target.
4. Check whether the old primary remained reachable to any clients
   after quorum moved away from it -- look for writes accepted on the
   old primary's logs with timestamps after the promotion event
   (evidence of a fencing gap).
5. Confirm the actual write acknowledgment/durability setting in use
   (e.g. Postgres `synchronous_commit`, MySQL semi-sync replication,
   MongoDB write concern) versus what the application assumes.

## Fix

Match the durability guarantee to what the application actually needs:
for data that cannot tolerate loss on failover, require synchronous or
semi-synchronous replication to at least one replica before
acknowledging the write, accepting the latency cost, or use a
consensus-based store (etcd/Raft-backed systems) for that specific
data instead of async-replicated databases. Where async replication is
kept for latency reasons, make the failover orchestrator lag-aware --
it must compare replica positions and either promote the most current
replica or refuse to fail over automatically (paging a human instead)
when the lag exceeds a defined safety threshold. Always fence the old
primary (STONITH, network isolation, or a generation/epoch fencing
token that older writes can't satisfy) before or during promotion so
it cannot accept further writes that the new primary will never see.

## Pitfalls

Don't "fix" this purely by shortening the failover detection timeout to
reduce the lag window -- a faster failover with the same async
replication still loses whatever was in flight, and an overly
aggressive timeout increases false-positive failovers during transient
blips, trading one failure mode for a more frequent one. Also don't
assume synchronous replication to a single standby eliminates the
problem: if that standby is in the same failure domain as the primary
(same rack, same availability zone), a correlated failure can still
take out both, so the replica used for durability guarantees must be
in a genuinely independent failure domain.

## Verify

Inject a controlled partition in a staging environment (e.g. block
replication traffic with an iptables rule or a chaos-engineering tool)
while a steady write load runs, trigger the failover path, and count
writes acknowledged to clients versus writes present on the promoted
replica -- the gap should be zero for synchronously replicated data
and bounded to a documented, monitored lag threshold for async data.
Confirm the old primary's write attempts after the partition are
rejected (fencing works) by checking its logs for connection refusals
or write failures during the promotion window.
