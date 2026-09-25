---
name: zookeeper-reelection-splits-cluster-brain
description: A ZooKeeper controller re-election during maintenance causes part of a Kafka cluster to elect a second controller, resulting in two clusters serving conflicting state.
triggers: ["kafka split brain zookeeper", "two kafka controllers elected", "zookeeper reprovisioning broke kafka", "kafka cluster split after zookeeper maintenance"]
permissions: ["READ"]
---

## Symptom

During or shortly after ZooKeeper maintenance (a node reprovisioning,
an upgrade, a network partition affecting the ZooKeeper ensemble), a
Kafka cluster ends up effectively split -- some brokers recognize one
controller, others recognize a different one, and producers/consumers
connected to different brokers observe inconsistent topic state, as if
two independent Kafka clusters briefly existed.

## Likely causes

- **A ZooKeeper ensemble member was reprovisioned (replaced, restarted)
  in a way that briefly changed quorum membership or connectivity**,
  causing a controller re-election to occur under ambiguous conditions --
  if network connectivity between broker groups and different ZooKeeper
  members is asymmetric during this window, different brokers can end up
  believing different controllers are authoritative.
- **A broker experiencing a ZooKeeper session timeout (due to GC pause,
  network blip, or resource contention) doesn't reliably detect and react
  to losing its session**, continuing to act on stale controller/
  leadership state after ZooKeeper has already moved on.
- **The ZooKeeper ensemble itself briefly lost quorum** (an
  under-provisioned or improperly sized ensemble, or too many members
  affected simultaneously by the maintenance) producing a genuinely
  ambiguous state rather than a single clear controller election.
- **Client and broker-side metadata caching means some clients continue
  routing produce/consume requests based on stale controller/partition-
  leader information** even after the cluster-side split is technically
  resolved, prolonging the appearance of inconsistency.

## Diagnose

1. Reconstruct the timeline of the ZooKeeper maintenance event precisely
   against Kafka controller election log entries (`controller.log` on
   each broker) to identify exactly when and how many controller
   elections occurred during the window.
2. Check for evidence of a genuine ZooKeeper quorum loss during the
   maintenance window (ZooKeeper's own logs showing leader election
   activity or quorum-related warnings) versus a Kafka-side-only issue.
3. Compare which specific brokers/partitions show inconsistent state
   (different apparent leaders for the same partition, or produce/
   consume requests routed inconsistently) to scope the actual blast
   radius.
4. Check broker-side ZooKeeper session timeout configuration against
   the actual GC pause / resource contention characteristics observed on
   affected brokers around the incident time.

## Fix

Perform ZooKeeper ensemble maintenance (member replacement, upgrades)
one member at a time with explicit verification that quorum is
maintained throughout, rather than operations that could affect multiple
members' availability simultaneously. Tune broker-side ZooKeeper session
timeout and GC behavior to minimize the window where a broker could hold
stale session state without detecting the loss. After any suspected
split, force a clean resynchronization (restarting affected brokers in a
controlled order so they re-establish ZooKeeper sessions and controller
state fresh) rather than assuming the cluster self-heals correctly, and
verify partition leadership is consistent across all brokers afterward.
Where feasible, migrate to KRaft mode (Kafka's ZooKeeper-free consensus,
available in modern Kafka versions), which removes this entire class of
issue by eliminating the separate ZooKeeper coordination layer.

## Pitfalls

Don't treat a resolved-looking cluster (brokers appear to be serving
traffic again) as proof the split is fully healed -- verify partition
leadership and in-sync-replica state explicitly across every broker,
since a split can leave subtly inconsistent metadata that only surfaces
later under specific conditions. Also don't perform ZooKeeper maintenance
during a period of already-elevated cluster load/instability, which
increases the chance of a borderline session-timeout scenario turning
into a real split.

## Verify

After the incident, audit every partition's leader and in-sync-replica
set across the entire cluster for consistency, and confirm no partition
shows conflicting leadership information from different brokers'
perspectives. For a genuinely reproducible test, simulate a controlled
ZooKeeper member restart in a non-production cluster and confirm
controller election completes cleanly with no observable window of
inconsistent broker state.
