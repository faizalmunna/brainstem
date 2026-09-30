---
name: elasticsearch-zero-downtime-reindex-for-mapping-fix
description: A reindex needed to correct a mapping mistake takes a very long time and risks downtime without an alias-based cutover strategy.
triggers: ["how to reindex elasticsearch without downtime", "reindex is taking forever", "change field type elasticsearch", "mapping is wrong need to reindex", "elasticsearch alias swap zero downtime"]
permissions: ["READ"]
---

## Symptom
A mapping mistake (wrong field type, missing multi-field, wrong
analyzer) is confirmed and the fix requires reindexing into a new index,
but the team either plans to write directly to the same index name during
a maintenance window (risking downtime and write loss), or kicks off a
naive `_reindex` against a live, large index and finds it runs for hours
while consuming significant cluster resources and racing against
ongoing writes to the original index.

## Likely causes
1. **Mappings for an existing field on an existing index cannot be
   changed in place** -- Elasticsearch only allows adding new fields to
   an existing mapping, not changing an existing field's type or core
   analysis settings, so any such fix inherently requires a new index,
   not an in-place update.
2. **Application code references the concrete index name directly**
   rather than an alias, so cutting over to a new index requires a
   coordinated code deploy timed against the reindex completion --
   exactly the situation an alias avoids.
3. **The source index is large enough that a single default `_reindex`
   call is slow and resource-intensive**, especially when run without
   `slices` for parallelism, and especially when the destination index's
   replicas are active during the bulk load (each replica re-does the
   indexing work).
4. **Writes continue to land on the original index during the reindex
   window**, so a reindex that captures a snapshot at time T misses
   everything written between T and cutover unless that gap is
   explicitly handled.

## Diagnose
- Confirm application code and any saved queries/dashboards reference an
  alias rather than a concrete index name -- `GET _alias` shows current
  alias-to-index mappings; if nothing points at the index via alias,
  that's the first gap to close before attempting a safe cutover.
- Estimate reindex duration and resource cost before running it at scale
  by test-reindexing a representative sample or checking `_reindex`
  progress via `GET _tasks?actions=*reindex&detailed=true` on a prior or
  in-progress run, rather than guessing.
- Check whether the destination index is created with replicas enabled
  during the bulk load -- `GET /<new-index>/_settings` -- since indexing
  into an index with active replicas duplicates indexing cost across
  every replica during the load.
- Confirm the actual live write rate on the source index
  (`GET /<index>/_stats/indexing`) to size how large a "catch-up" gap
  the reindex will need to cover after the initial bulk copy.

## Fix
- Adopt an alias-based pattern before this situation recurs: application
  code and dashboards always read/write through an alias
  (`my-index-current`) that points to a concrete, versioned index name
  (`my-index-v3`) behind the scenes -- cutover then becomes an atomic
  alias swap, not a code change.
- Create the new index (`my-index-v4`) with the corrected mapping and
  `number_of_replicas: 0` during the bulk load, then run `_reindex` with
  `slices: auto` for parallelism across shards, monitoring via
  `GET _tasks`.
- After the bulk reindex completes, run a second, narrower `_reindex`
  filtered by a timestamp/version-cursor query covering only documents
  written since the bulk reindex started, to catch up on writes that
  landed during the long-running copy -- repeat this narrowing catch-up
  pass until the remaining delta is small enough to complete within an
  acceptable pause window (or brief write-pause) for the final swap.
- Set the new index's replica count back to the desired value and wait
  for it to go green, then atomically swap the alias
  (`POST _aliases` with a `remove` for the old index and `add` for the
  new index in the same request) so there's no window where the alias
  points at neither or both in a way that causes duplicate/missing
  results.

## Pitfalls
- Swapping the alias with two separate calls (remove old, then add new)
  instead of one atomic `_aliases` request creates a real window where
  the alias resolves to nothing, causing application errors during
  exactly the cutover moment the alias pattern was meant to avoid.
- Forgetting the catch-up reindex pass (assuming the bulk `_reindex`
  alone is a complete, current snapshot) silently drops any documents
  written during the bulk copy's runtime, which can be a large gap on
  a busy index with a multi-hour reindex.
- Running the bulk reindex with the destination index's normal replica
  count from the start roughly doubles (or more) indexing cost during
  the load for no benefit, since replicas aren't needed for query
  correctness until the index is actually serving traffic.

## Verify
After the alias swap, confirm `GET _alias/my-index-current` (or
whatever alias name is used) resolves to the new index, run
`GET /my-index-current/_count` and compare against the pre-cutover
document count on the old index (accounting for any expected delta from
ongoing writes), and spot-check that the specific mapping fix (field
type, analyzer) behaves correctly against a few known documents before
decommissioning the old index.
