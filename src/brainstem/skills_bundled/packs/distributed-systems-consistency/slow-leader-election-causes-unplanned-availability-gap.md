---
name: slow-leader-election-causes-unplanned-availability-gap
description: A consensus algorithm's leader election takes far longer than expected under certain network conditions, creating an availability gap that SLA planning never accounted for.
triggers: ["leader election took too long", "raft election taking minutes", "availability gap during failover exceeded slo", "consensus cluster unavailable during election"]
permissions: ["READ"]
---

## Symptom

A Raft/Paxos-based system (etcd, Consul, CockroachDB, a custom
consensus layer) experiences a leader failure or network event, and
the cluster is unavailable for writes (and sometimes reads) for far
longer than the "typical" failover time engineers had in mind when
setting SLAs -- seconds turn into tens of seconds or minutes. Nothing
is technically broken; the algorithm eventually elects a leader
correctly, but the gap blows through the availability budget nobody
had actually tested against realistic conditions.

## Likely causes

- **Election timeout and heartbeat interval settings weren't tuned
  for the actual network's latency/jitter characteristics**, especially
  across regions -- default configurations often assume low, stable
  latency (single data center) and behave very differently across a
  WAN link with variable latency.
- **Repeated split votes**: multiple nodes time out and start an
  election simultaneously (common with synchronized election timeouts
  or too few nodes), no candidate gets a majority, and the cluster
  cycles through several failed election rounds before randomized
  backoff finally staggers them enough to succeed.
- **A flapping or partially-failed network link causes repeated
  leadership churn** -- a node that can reach some but not all peers
  keeps triggering elections it can't cleanly win or lose, extending
  the unavailability window well past a single clean election.
- **Client-side retry/reconnect logic amplifies the perceived outage**
  -- even after the cluster elects a new leader promptly, clients with
  long connection timeouts, no backoff, or stale leader-address
  caching take much longer to discover and reconnect to the new
  leader, so the user-visible gap is longer than the actual election
  duration.

## Diagnose

1. Pull the consensus layer's own election logs (Raft term changes,
   vote requests/grants, leader-transition timestamps) for the
   incident and measure the actual wall-clock time from leader loss to
   a stable new leader, separate from any client-visible impact.
2. Count the number of election terms/rounds that occurred during the
   gap -- a single clean election completing in one term points at a
   simple timeout-tuning issue, while many terms in quick succession
   points at split votes or network flapping.
3. Check the configured election timeout and heartbeat interval
   against measured inter-node network latency and jitter (not the
   theoretical same-datacenter latency) for the actual deployment
   topology, especially for cross-region clusters.
4. Check network telemetry for the incident window for partial
   connectivity (some node pairs degraded, not all) rather than a
   clean full partition, which would explain repeated churn instead
   of one clean transition.
5. Separately measure client reconnect behavior: how long after the
   new leader was elected did clients actually start succeeding again,
   and check client-side retry/backoff/leader-discovery configuration
   for that gap.

## Fix

Tune election timeout and heartbeat interval against the real,
measured latency distribution of the deployment's network (including
tail latency and cross-region jitter, not just median same-AZ
latency), following the consensus algorithm's documented guidance for
the ratio between heartbeat interval and election timeout. Use
randomized election timeouts (most modern Raft implementations
support this) with a wide enough jitter range to make simultaneous
election starts across nodes unlikely, reducing split-vote frequency.
For deployments spanning regions with meaningfully different latency
characteristics, consider a topology that weights voting/leadership
toward the region with the best connectivity (e.g. non-voting learner
nodes in high-latency regions) rather than treating all nodes as
electively equal. On the client side, implement leader discovery with
short, bounded retries and exponential backoff, and avoid caching a
leader address without a freshness check, so client-visible recovery
time tracks the actual election time rather than adding its own delay
on top. Feed the *measured* (not theoretical) election time into SLA/
capacity planning explicitly, including a realistic worst case from
game-day testing, not the best-case single-clean-election number.

## Pitfalls

Don't tune election timeouts down aggressively to "fix" a slow
election without addressing the underlying network jitter -- a timeout
set too tight relative to real jitter increases spurious elections
under normal conditions, trading a rare long outage for frequent short
ones, which is often worse for aggregate availability. Also don't
treat the consensus algorithm's own election time as the whole
availability gap in SLA documents -- client reconnect behavior is
frequently the larger and more fixable contributor, and ignoring it
means the SLA stays wrong even after tuning the consensus layer
correctly.

## Verify

Run a game-day exercise that kills the current leader under
production-like network conditions (including realistic cross-region
latency if applicable) and measure, separately, the consensus layer's
own re-election time and the end-to-end client-visible unavailability
time. Repeat under an injected partial-network-degradation scenario
(not just a clean node kill) to confirm the tuned timeouts don't
produce repeated election churn, and confirm the measured numbers are
now within whatever SLA/error-budget figure was updated to reflect
them.
