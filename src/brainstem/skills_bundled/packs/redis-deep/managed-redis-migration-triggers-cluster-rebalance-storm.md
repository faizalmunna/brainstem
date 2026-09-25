---
name: managed-redis-migration-triggers-cluster-rebalance-storm
description: A cloud provider's automatic migration of a primary Redis instance to new underlying hardware triggers a cluster rebalance that cascades into broader application failures.
triggers: ["redis migration caused outage", "managed redis instance move broke cluster", "redis cluster rebalance cascading failure", "cloud redis maintenance caused downtime"]
permissions: ["READ"]
---

## Symptom

A cloud provider performs a routine, supposedly transparent migration or
maintenance operation on a managed Redis primary instance (moving it to
new underlying hardware), and instead of being seamless, it triggers a
cluster rebalance that cascades into elevated latency, connection
errors, and application-level failures well beyond the migration's own
brief window.

## Likely causes

- **Application clients don't handle a brief primary failover/
  reconnection gracefully** -- connection pools hold stale connections to
  the old primary address, and reconnection logic (if it exists at all)
  retries aggressively enough to create a thundering-herd reconnection
  storm right as the new primary becomes available.
- **The migration triggers a cluster-wide rebalance (in a Redis Cluster
  topology) rather than a simple primary swap**, and rebalancing itself
  temporarily redistributes slot ownership, causing a wave of
  MOVED/ASK redirections that overwhelmed clients weren't designed to
  handle efficiently at volume.
- **Downstream services treat any Redis error (even a transient one
  during failover) as a hard failure** rather than a retryable condition,
  propagating a brief Redis-side blip into a much larger application-
  level outage.
- **No jitter/backoff exists on client reconnection attempts**, so many
  application instances reconnecting simultaneously after the same
  migration event create a burst of connection load that itself looks
  like (and can cause) an overload, independent of Redis's own recovery
  time.

## Diagnose

1. Correlate the exact timeline of the cloud provider's migration/
   maintenance event against the application's own error spike, to
   confirm the migration is the actual trigger versus a coincidental,
   unrelated issue.
2. Check application logs for connection errors and reconnection
   patterns during the incident window -- specifically whether
   reconnections happened in a tight burst (thundering herd) or spread
   out reasonably.
3. Check whether the topology is Redis Cluster (with slot-based sharding
   and rebalancing) versus a simple primary-replica setup, since the
   failure mode differs meaningfully between the two.
4. Review client-side error handling for Redis operations -- confirm
   whether transient errors during the migration window were retried
   gracefully or treated as immediate hard failures.

## Fix

Implement client-side connection retry with exponential backoff and
jitter specifically for Redis connection failures, so a brief failover
doesn't produce a simultaneous reconnection storm across all application
instances. Ensure connection pools detect and discard stale connections
to a now-defunct primary promptly rather than continuing to attempt use
of them. Treat transient Redis errors (connection reset, MOVED
redirections during rebalance) as retryable at the application layer
rather than immediate hard failures, with a reasonable number of retries
before genuinely failing the operation. Where the cloud provider offers
a choice of maintenance window timing, schedule migrations during lower-
traffic periods to reduce blast radius if a brief disruption does occur
despite these mitigations.

## Pitfalls

Don't assume a cloud provider's "seamless"/"zero-downtime" migration
claim means the application doesn't need its own resilience -- even a
genuinely brief interruption can cascade badly if application-side
reconnection/retry logic isn't robust, as this exact pattern has caused
real production incidents. Also don't add retries without backoff/jitter
-- naive immediate retries can make a reconnection storm worse, not
better.

## Verify

Simulate a Redis primary failover in a non-production environment (many
managed Redis offerings support a manual failover trigger for testing)
and confirm the application reconnects gracefully with bounded,
staggered reconnection load and no cascading application-level errors.
Confirm the fix holds up under realistic production traffic levels, not
just a low-traffic test environment.
