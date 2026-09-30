---
name: network-partition-primary-crashes-read-only-mode
description: A network partition affecting a Redis primary causes it to crash or restart into a read-only replica state, silently breaking application writes that expected the primary role to persist.
triggers: ["redis primary crashed after network partition", "redis unexpectedly read only", "redis master demoted unexpectedly", "writes failing redis read only mode"]
permissions: ["READ"]
---

## Symptom

Following a network partition or connectivity blip affecting a Redis
primary node, the application starts receiving errors indicating Redis
is in read-only mode, or write operations silently fail -- the primary
node that used to accept writes is no longer willing to (or is no longer
the actual primary), and the application wasn't designed to detect or
react to this role change.

## Likely causes

- **A Redis Sentinel or cluster-based failover mechanism detected the
  partitioned primary as unreachable and promoted a replica to primary**,
  but the application's client is still configured with (or cached) the
  address of the old, now-demoted node, which correctly refuses writes
  in its new replica role.
- **The original primary, after recovering from the partition, rejoined
  the cluster as a replica of the newly promoted primary** (correct
  cluster behavior to avoid split-brain), but any in-flight application
  logic still assumed it was the primary and continued sending writes to
  it, which are now correctly rejected.
- **A retry mechanism (e.g. in a billing or payment flow) repeatedly
  retried a failed operation against a node stuck in read-only state
  without ever discovering and switching to the actual current
  primary**, compounding the impact of the original partition well
  beyond its actual duration.
- **The application has no Sentinel-aware or cluster-aware client
  configured** -- it connects to a fixed, specific node address rather
  than discovering the current primary dynamically, so any failover
  (planned or unplanned) breaks writes until manual intervention updates
  the configured address.

## Diagnose

1. Check Redis Sentinel (or cluster) logs for the actual failover event
   timeline -- when the partition was detected, when a new primary was
   elected, and when/whether the original primary rejoined.
2. Check the application's Redis client configuration for whether it
   uses Sentinel-aware/cluster-aware discovery (dynamically finding the
   current primary) or a static, hardcoded node address.
3. Check application logs for repeated failed write attempts during and
   after the incident, and confirm whether retries were being made
   against a now-read-only node rather than the current actual primary.
4. Confirm the actual current primary/replica role assignment post-
   incident matches what the application believes it's talking to.

## Fix

Use a Sentinel-aware or cluster-aware Redis client library that
dynamically discovers the current primary rather than connecting to a
fixed address, so a failover (planned maintenance or unplanned partition)
is transparent to the application without manual reconfiguration. Ensure
retry logic for Redis operations checks/re-resolves the current primary
on a write failure rather than blindly retrying against the same
(possibly now-demoted) node. For operations where write durability
genuinely matters (billing, critical state), consider whether Redis is
the appropriate store at all versus a system with stronger consistency
guarantees during partition scenarios, or add explicit write
confirmation/idempotency so a retried operation after a role change
doesn't produce a duplicate or lost effect.

## Pitfalls

Don't disable Sentinel's automatic failover to avoid this class of issue
-- automatic failover is what limits the duration of a real outage during
a genuine primary failure; the fix is making the application client
failover-aware, not removing the failover mechanism itself. Also don't
assume a "successful" write retry after a failover actually landed
correctly without verifying -- confirm the write actually reached the new
primary and wasn't silently dropped during the transition window.

## Verify

Simulate a primary failure/partition in a non-production Sentinel or
cluster setup and confirm the application's client automatically
discovers and switches to the new primary, resuming writes without
manual intervention or extended failure. Confirm no writes are
duplicated or lost across the simulated failover for operations with
retry logic.
