---
name: quorum-write-succeeds-but-stale-node-serves-read
description: A quorum-based write reports success but a subsequent read is served by a node that never received it, returning a stale value despite a healthy quorum.
triggers: ["quorum write succeeded but read is stale", "dynamo style quorum returning old data", "read repair not triggering", "R plus W not greater than N misconfigured"]
permissions: ["READ"]
---

## Symptom

A Dynamo-style quorum system (Cassandra, Riak, DynamoDB-like
configurations with tunable consistency) reports a write as
successful because it satisfied its write quorum (W), but a later read
occasionally returns the old value even though no node crashed and no
partition is ongoing. This is distinct from ordinary replication lag
because the read itself claims to be quorum-consistent -- the system's
own consistency contract (R + W > N) appears violated, which is what
makes it alarming rather than an expected async-replication delay.

## Likely causes

- **R + W does not actually exceed N** for the configured replication
  factor and consistency levels in use -- a common misconfiguration is
  assuming "quorum" consistency levels on both read and write
  automatically satisfy this, without checking the actual numeric
  values (e.g. N=3 with W=1/R=1 "quorum" settings misapplied, or N
  changed during a topology change without updating R/W assumptions).
- **A topology change (adding/removing nodes, changing replication
  factor) happened between the write and the read**, and the set of
  replicas responsible for the key shifted -- the write's quorum was
  correct for the old topology, but the read's quorum queried a
  different, now-current set of replicas that don't fully overlap.
- **Hinted handoff or read repair is enabled but hasn't completed**
  -- a replica that was down during the write received a "hint" to
  replay later instead of the write directly, and if the read happens
  to hit that replica plus enough others before the hint replays or
  read-repair reconciles it, a stale value can still be returned
  depending on reconciliation timing and conflict resolution.
- **Client-side consistency-level settings differ between the write
  path and the read path** -- e.g. one service in a shared codebase
  writes at QUORUM while a different service (or an older client
  library version) added later reads at ONE for performance, silently
  breaking the R+W>N invariant the original design relied on.

## Diagnose

1. Pull the actual N (replication factor), W (write consistency
   level), and R (read consistency level) values in effect at the
   time of the incident -- from configuration, not assumption -- and
   compute whether R + W > N genuinely held.
2. Check the cluster's topology-change history (node adds/removes,
   token/range reassignment events) around the incident window for
   overlap with the write and read timestamps in question.
3. Check hinted-handoff and read-repair status/metrics for the
   specific key's replica set -- was any replica down at write time,
   and had its hint replayed or read-repair completed before the read
   in question?
4. Trace the specific read and write requests to confirm exactly
   which consistency level each one actually used at the client
   level, since defaults can differ silently between library versions
   or services.
5. Query all N replicas for the key directly (bypassing the normal
   quorum read path, e.g. per-node debug queries) to see the actual
   divergent values and which specific replica(s) were behind.

## Fix

Explicitly compute and enforce R + W > N for the replication factor
actually in use, and treat any change to N (adding nodes, changing
replication factor) as requiring a review of R/W settings, not an
independent operational action. Standardize the consistency level
used across every service that reads or writes a given keyspace/table
(via a shared client configuration or wrapper, not per-service
defaults) so the invariant can't be silently broken by one service
choosing a weaker level for latency reasons. Monitor hinted-handoff
queue depth and read-repair lag as first-class metrics, and treat a
growing hint backlog as an active correctness risk, not just a
capacity concern -- alert before it becomes large enough to make
stale reads likely. During planned topology changes, follow the
datastore's documented safe procedure (e.g. Cassandra's requirement to
run repair after topology changes) rather than assuming quorum math
alone keeps things consistent through a transition.

## Pitfalls

Don't assume "quorum" as a named consistency level automatically
means R + W > N is satisfied -- some systems' "QUORUM" is defined
relative to the *current* N and can be temporarily wrong during a
topology change, and mixing named levels (QUORUM) with numeric
overrides elsewhere is a common source of an inconsistent effective
policy. Also don't treat a resolved stale-read incident as fixed just
because the immediate read now returns the correct value -- if the
root cause was an R+W misconfiguration, the same gap will recur on
the next topology change unless the configuration itself, not just
the symptom, is corrected.

## Verify

Recompute and document R + W > N for every keyspace/table's actual
production configuration, and add an automated check (a config
linter or a startup assertion) that fails deployment if a service's
consistency-level settings would violate the invariant for the
cluster's current N. Run a controlled test that performs a write,
immediately triggers a topology change (add or remove a node) in a
staging cluster, then performs a quorum read, confirming the correct
post-write value is returned throughout the transition.
