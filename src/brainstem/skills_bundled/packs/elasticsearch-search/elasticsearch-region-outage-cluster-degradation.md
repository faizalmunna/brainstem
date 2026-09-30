---
name: elasticsearch-region-outage-cluster-degradation
description: A managed Elasticsearch or OpenSearch deployment degrades severely or becomes unavailable during an underlying cloud region-level outage, beyond what node-level redundancy alone should allow.
triggers: ["elasticsearch cluster down during aws outage", "elastic cloud unavailable region outage", "managed opensearch degraded during cloud incident", "cluster red during aws us-east-1 outage", "how resilient is our cluster to a region outage"]
permissions: ["READ"]
---

## Symptom
During a broader cloud provider region-level incident (a well-documented,
recurring real-world pattern -- e.g. AWS region-level outages have
repeatedly caused severe, hours-long degradation for Elastic Cloud and
other managed-Elasticsearch/OpenSearch deployments hosted in the affected
region), the cluster doesn't just see elevated latency proportional to
lost capacity -- it goes fully red/unavailable, master election fails
outright, or recovery takes far longer than the underlying outage itself
once the region recovers.

## Likely causes
1. **All nodes (data and master-eligible) are provisioned in a single
   region, or even a single availability zone within it**, so a
   region-level (or zone-level) cloud outage removes a large fraction or
   all of the cluster's capacity simultaneously rather than the partial,
   tolerable loss the cluster's replica/quorum design assumes.
2. **Master-eligible node count and placement don't provide real quorum
   resilience across zones** -- e.g. 3 master-eligible nodes exist, but
   2 of the 3 happen to sit in the single zone most affected by the
   outage, so the surviving node count drops below the quorum needed to
   elect a master, halting the entire cluster even though some capacity
   survives.
3. **Dependent managed-service control planes (snapshot storage, the
   cloud provider's own orchestration API used by the managed
   Elasticsearch/OpenSearch service to manage nodes) are themselves
   impacted by the same region outage**, so even automated failover or
   node-replacement mechanisms the managed service relies on are
   degraded at the exact moment they're needed.
4. **Recovery after the region comes back is slow because a large
   fraction of shards need to reallocate/recover simultaneously** (all
   at once, competing for the same recovery bandwidth and disk I/O),
   rather than a small, steady trickle of shard movement the cluster
   handles routinely.

## Diagnose
- Review actual node/zone placement (`GET _cat/nodes?v&h=name,node.role,
  ip` cross-referenced with the cloud provider's zone assignment for each
  node's IP/instance) to confirm whether nodes are genuinely spread
  across multiple availability zones, not just labeled as such.
- Check master-eligible node count and zone distribution specifically
  (`GET _cat/nodes?v&h=name,master,node.role` filtered to master-eligible
  nodes) -- confirm quorum (a strict majority of master-eligible nodes)
  can survive the loss of any single zone, not just any single node.
- During or after an incident, check the cloud provider's own status page
  and post-incident report for which specific zone(s)/services were
  affected, and cross-reference against which of the cluster's nodes and
  the managed service's control-plane dependencies sit in those zones.
- Review `cluster.routing.allocation.awareness` configuration
  (`GET _cluster/settings`) to confirm shard allocation awareness is
  actually configured to spread primary/replica pairs across zones --
  without this, replicas can end up concentrated in the same zone as
  their primary, defeating the purpose of multi-zone placement.

## Fix
- Distribute data nodes and, critically, master-eligible nodes across at
  least three availability zones within the region (or across regions
  for the highest resilience tier, if the managed service and use case
  support cross-region clusters), sized so quorum survives the loss of
  any one zone.
- Configure `cluster.routing.allocation.awareness.attributes` with a zone
  attribute so Elasticsearch actively avoids placing a primary and all
  its replicas in the same zone, ensuring a zone loss doesn't take out
  every copy of any shard.
- For workloads where full regional resilience is a genuine business
  requirement (not just node-level resilience), evaluate cross-region
  replication (cross-cluster replication, or application-level dual-
  write/reindex to a standby cluster in a second region) understanding
  this is a meaningfully larger operational and cost commitment than
  multi-zone placement within one region.
- Size expected recovery time realistically: test (in a non-production
  environment) how long shard recovery actually takes after simulating
  loss of a full zone's worth of nodes, rather than assuming recovery
  time scales linearly from single-node-loss experience.

## Pitfalls
- Assuming a managed service's marketing description of "highly
  available" or "multi-AZ" is automatically true for a specific
  cluster's actual configuration -- multi-AZ capability being available
  from the provider doesn't guarantee a given cluster was actually
  provisioned to use it; verify actual node placement directly.
- Treating this purely as an Elasticsearch configuration problem while
  ignoring that the managed service's own control plane and the
  application's other dependencies (databases, message queues) may share
  the same region-outage blast radius -- a resilience plan needs to
  account for the whole dependency chain, not just the search cluster.
- Over-investing in cross-region active-active replication for a
  workload that could tolerate a documented, bounded recovery-time
  objective from a well-architected multi-zone single-region setup --
  match the resilience investment to the actual business requirement,
  since cross-region replication carries real ongoing operational cost
  and consistency complexity.

## Verify
Run a game-day exercise (in a non-production or clearly scoped
environment) simulating the loss of an entire availability zone's nodes
and confirm the cluster maintains master quorum and stays available
(possibly degraded, but not fully red) throughout, and confirm actual
recovery time once the simulated zone returns matches the organization's
recovery-time expectations rather than being discovered for the first
time during a real incident.
