---
name: coordination-service-reelection-causes-split-brain-clusters
description: A coordination service re-election during a network event leaves a cluster split into two groups that each believe they are the sole authoritative leader.
triggers: ["split brain after leader election", "two nodes think they are primary", "cluster split into two groups serving different state", "coordination service reelection caused split brain"]
permissions: ["READ"]
---

## Symptom

After a network partition, a coordination-service (ZooKeeper, etcd,
Consul) maintenance event, or a slow/failed heartbeat, a cluster
that should have exactly one leader ends up with two: each half
continues serving reads and accepting writes independently, believing
it is authoritative. Clients connected to different nodes see
diverging state, and when the partition heals, the two sides have
irreconcilable conflicting writes with no clear "correct" version.

## Likely causes

- **The old leader doesn't reliably detect that it has lost its lease
  or session** (a GC pause, slow disk I/O, or CPU starvation delays it
  from noticing its heartbeat/session expired), so it keeps acting as
  leader after the coordination service has already elected a new one
  elsewhere.
- **The coordination service ensemble itself lost quorum or split**
  during the network event, producing two groups of coordination nodes
  that each believe they hold quorum and can therefore each grant a
  leader lease independently -- this is a genuine split at the
  consensus layer, not just an application-level bug.
- **No fencing mechanism exists to physically prevent the demoted
  leader from performing leader actions** (writing to shared storage,
  accepting client writes, sending to a message bus) even after a new
  leader is elected -- election alone doesn't stop the old leader from
  acting, it only elects a replacement.
- **Lease/session timeout values are too tight relative to realistic
  GC pause or network jitter**, causing spurious re-elections under
  normal load that increase the frequency of the dangerous overlap
  window rather than genuine failures.

## Diagnose

1. Pull leader-election logs from the coordination service for the
   exact incident window and reconstruct the sequence: when the old
   leader's session/lease expired, when the new leader was elected,
   and whether there's a gap where both existed.
2. Check the old leader's own process logs/metrics (GC logs, disk I/O
   latency, CPU) for evidence it was unresponsive or delayed around
   the session-expiry timestamp -- this distinguishes "leader was slow
   to notice" from "coordination service itself split."
3. Check the coordination-service ensemble's own internal consensus
   logs (ZooKeeper's own leader election, etcd's Raft term/leader
   changes) for evidence of a quorum loss or ensemble-level split
   coincident with the application-level split.
4. Diff the data/state each side wrote during the overlap window to
   scope exactly which records are in conflict and confirm both sides
   really were accepting writes (not just holding stale reads).
5. Check whether a fencing token or generation number was in use, and
   if so, whether any downstream system (storage, message queue)
   actually validated it and rejected stale writes.

## Fix

Require every leadership change to carry a monotonically increasing
fencing token (an epoch/generation number), and make every
downstream system that a leader writes to reject writes from a lower
token than one it has already seen -- this makes the old leader's
actions harmless even if it doesn't know it's been demoted, rather
than relying on the old leader "noticing" in time. Size session/lease
timeouts against measured worst-case GC pause and network jitter, not
optimistic averages, so re-elections aren't triggered by ordinary
transient slowness. For the coordination service itself, run an odd
number of ensemble members spread across independent failure domains
so a single network partition can't produce two groups that each
believe they hold quorum. Where the coordination layer can be
simplified, prefer designs with built-in fencing (e.g. Raft-based
leases with epoch numbers) over bolting fencing on afterward.

## Pitfalls

Don't treat "a new leader was elected" as proof the old leader stopped
acting -- election and fencing are separate concerns, and skipping
fencing because "the old leader should shut down gracefully" fails
exactly in the slow-GC/network-partition cases that matter most.
Also don't respond to a split-brain incident by simply shortening
lease timeouts across the board; without fixing the underlying
GC/I/O pause or improving fencing, a shorter timeout just makes
spurious re-elections (and therefore split-brain windows) more
frequent, not less likely.

## Verify

In a non-production environment, simulate the failure directly: pause
the current leader process (e.g. `SIGSTOP` or a cgroup freeze) long
enough to trigger re-election, then resume it and confirm its writes
are rejected by downstream systems due to a stale fencing token while
the new leader's writes succeed. Separately, simulate a coordination-
ensemble network partition and confirm only one side can achieve
quorum and grant a lease -- the minority side should refuse to elect
a leader at all rather than electing its own.
