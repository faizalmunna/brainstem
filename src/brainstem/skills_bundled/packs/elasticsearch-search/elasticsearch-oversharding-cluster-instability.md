---
name: elasticsearch-oversharding-cluster-instability
description: A cluster has far more shards than its data volume or node count justifies, causing slow cluster state updates, slow query coordination, and unstable master nodes.
triggers: ["too many shards elasticsearch", "cluster state update slow", "elasticsearch cluster unstable master", "why is my cluster so slow with small indices", "shard count warning", "cluster health slow to respond"]
permissions: ["READ"]
---

## Symptom
Cluster-level operations (creating an index, updating a mapping, cluster
health checks) get progressively slower and occasionally time out, master
node CPU stays elevated even during otherwise idle periods, and simple
queries against small indices take longer than the data volume would
suggest -- despite no individual index looking obviously overloaded.
Elasticsearch's own shard-count deprecation warnings may already be
appearing in logs.

## Likely causes
1. **A daily-rolling-index pattern with a fixed shard count per index,
   applied to a low-volume data stream.** Creating 5 primary shards for
   an index that only ever holds a few hundred MB per day means most
   shards are a few tens of MB -- far below the recommended range (tens
   of GB) -- multiplying shard count without any benefit to parallelism.
2. **Shard count decided once at index-creation time and never revisited**
   as data volume changed, either because the source volume dropped
   after being provisioned for a peak that never recurred, or because a
   copy-pasted index template from a much larger index was reused.
3. **Every shard (primary and replica) consumes cluster state and
   per-shard heap/file-handle overhead on every node that holds it**,
   independent of how much data is in it -- so thousands of near-empty
   shards degrade cluster state propagation and search-coordination
   fan-out even though total data volume is modest.
4. **Index templates or ILM (index lifecycle management) policies rolling
   over on a time interval rather than a size/doc-count threshold**,
   producing many small indices (each with their own shard set) for
   naturally bursty or low-traffic data.

## Diagnose
- Run `GET _cluster/health` and check `active_shards` against total
  cluster data volume (`GET _cat/indices?v&s=store.size` summed) -- as a
  rule of thumb, average shard size well under a few GB across the
  cluster is a strong oversharding signal.
- Run `GET _cat/shards?v` and look for a large number of shards each
  reporting a tiny `store` size (megabytes, not gigabytes).
- Check `GET _nodes/stats/jvm` for master-eligible nodes and correlate
  heap/GC pressure with cluster state size -- `GET _cluster/state
  | wc -c` (via `_cluster/state?pretty` size) growing into many MB is a
  direct symptom of too many shards/indices/mappings tracked in cluster
  state.
- Review index templates and ILM policies for rollover conditions based
  purely on `max_age` rather than `max_primary_shard_size` or
  `max_docs`, which is what produces many small indices/shards on
  variable-volume data.

## Fix
- Consolidate low-volume time-based indices: use ILM rollover conditions
  based on `max_primary_shard_size` (e.g. roll over at ~30-50GB per
  primary shard) or `max_docs` in addition to `max_age`, so shard count
  scales with actual data volume rather than a fixed calendar interval.
- Reduce the primary shard count in the index template for new indices
  going forward to match realistic volume (as a starting heuristic, size
  each primary shard to end up in the tens-of-GB range, not hundreds of
  MB) -- existing indices' primary shard count can't be changed in
  place, so apply this via the template and let old indices age out, or
  use `_shrink` on an existing index to reduce its primary shard count
  once it's no longer being written to.
- Use `_shrink` (for reducing primary shards on a read-only index) or a
  reindex into a new index with the corrected shard count for historical
  indices that are already oversharded and still queried often enough to
  matter.
- Consider `searchable snapshots` or simply deleting/closing very old,
  rarely-queried small indices instead of keeping them fully allocated
  with live shards indefinitely, if retention requirements allow it.

## Pitfalls
- Overcorrecting to a single primary shard per index to "fix"
  oversharding removes the ability to parallelize search/indexing across
  nodes for that index -- the goal is right-sizing shard count to data
  volume and node count, not minimizing it unconditionally.
- Running `_shrink` without first setting the index to read-only
  (`index.blocks.write: true`) and confirming all its shards are
  allocated to a single node first will fail -- `_shrink` requires this
  as a precondition, not an optional step.
- Reducing shard count without also checking replica count multiplies
  the fix's impact or lack thereof -- a single primary with 3 replicas is
  still 4x the per-shard overhead per index copy.

## Verify
After applying template changes, confirm new indices created under ILM
roll over at the intended shard size (`GET _cat/shards?v` on the new
index shows shard sizes in the target range once populated), and confirm
`GET _cluster/health` shard counts trend down over the ILM retention
window as old oversharded indices age out, alongside reduced master node
CPU/heap usage in `GET _nodes/stats`.
