---
name: elasticsearch-unassigned-shards-disk-watermark
description: Cluster status goes yellow or red with unassigned shards after a node loss, and disk-based allocation watermarks block automatic reallocation.
triggers: ["cluster status yellow unassigned shards", "cluster status red", "disk watermark exceeded elasticsearch", "shards not reallocating after node loss", "flood stage watermark", "unassigned_shards not recovering"]
permissions: ["READ"]
---

## Symptom
After a node restarts, is replaced, or is lost, `GET _cluster/health`
stays yellow (replicas unassigned) or red (primaries unassigned) far
longer than expected, and shards don't reallocate on their own even
though healthy nodes with apparent free capacity are in the cluster.

## Likely causes
1. **Disk-based shard allocation watermarks are blocking allocation on
   the remaining nodes.** By default, Elasticsearch stops allocating new
   shards to a node once it crosses the "low" watermark (typically 85%
   disk used), and actively relocates shards away from a node past the
   "high" watermark (90%), and enforces a read-only index block at the
   "flood stage" watermark (95%) -- if remaining nodes are already near
   these thresholds, losing a node's capacity pushes the rest over the
   line and halts reallocation entirely.
2. **Not enough nodes exist to satisfy replica allocation awareness
   rules** -- e.g. shard allocation awareness configured for
   availability zones, and the lost node was the only remaining node in
   its zone able to hold a replica without violating the awareness
   constraint.
3. **The lost node held the only copy of a primary shard with zero
   replicas configured**, which is unassigned-and-unrecoverable (red,
   not yellow) until that node returns, since there is no replica to
   promote.
4. **`cluster.routing.allocation.enable` was left set to `none` or
   `primaries` from a prior maintenance operation** (e.g. a rolling
   restart procedure that disabled allocation and was never re-enabled),
   which blocks normal reallocation entirely regardless of disk space.

## Diagnose
- Run `GET _cluster/allocation/explain` -- this is the direct diagnostic
  for "why is this shard unassigned," and returns the specific blocking
  reason (disk watermark, awareness constraint, allocation disabled,
  no valid node) rather than requiring guesswork.
- Check `GET _cat/allocation?v` to see disk usage percentage per node and
  compare against the configured watermark percentages in
  `GET _cluster/settings?include_defaults=true` (look for
  `cluster.routing.allocation.disk.watermark.*`).
- Check `GET _cluster/settings` for `cluster.routing.allocation.enable`
  being anything other than `all`, which would indicate allocation was
  deliberately disabled and not restored.
- If shard allocation awareness is configured
  (`cluster.routing.allocation.awareness.attributes`), confirm via
  `GET _cat/nodes?v&h=name,node.role,attr` how many nodes remain in each
  awareness zone/attribute value.

## Fix
- If disk watermarks are the blocker, free up disk space on the affected
  nodes (delete old/unneeded indices, especially oversharded historical
  indices per `elasticsearch-oversharding-cluster-instability`) or add
  storage/nodes rather than simply raising the watermark percentages,
  since raising watermarks just moves the same problem to a slightly
  higher fill level without addressing the actual capacity shortfall.
- If allocation was disabled for maintenance and never restored, run
  `PUT _cluster/settings` with
  `"cluster.routing.allocation.enable": "all"` to resume normal
  allocation.
- If awareness constraints can't be satisfied because a zone lost its
  only eligible node, either restore a node in that zone or, as a
  temporary and consciously-risky measure, relax
  `cluster.routing.allocation.awareness.force.*.values` requirements
  until capacity is restored -- understanding this temporarily reduces
  the actual cross-zone redundancy guarantee.
- For a genuinely lost primary with no replica (red status, unrecoverable
  without the original node), restore from snapshot if one exists;
  going forward, set `number_of_replicas` to at least 1 for any index
  where data loss from a single node failure is unacceptable.

## Pitfalls
- Raising disk watermark percentages as a first response (rather than
  freeing real capacity) postpones the problem to a fuller disk and
  increases the risk of actually running out of disk space entirely,
  which is a much worse failure mode than temporarily unassigned shards.
- Manually forcing shard allocation with
  `POST _cluster/reroute?retry_failed=true` repeatedly without addressing
  the root blocking condition just causes the same shards to fail
  allocation again on the next automatic pass -- use
  `_cluster/allocation/explain` to fix the actual cause first.
- Setting `cluster.routing.allocation.enable` to `all` without confirming
  disk space is actually available can trigger a burst of shard movement
  that itself further fills already-tight disks, worsening the situation
  -- confirm capacity is genuinely resolved first.

## Verify
Run `GET _cluster/health` and confirm status returns to green
(`unassigned_shards: 0`), and run `GET _cat/allocation?v` to confirm disk
usage on all nodes is comfortably under the low watermark rather than
hovering just beneath it, which would risk recurrence on the next minor
capacity fluctuation.
