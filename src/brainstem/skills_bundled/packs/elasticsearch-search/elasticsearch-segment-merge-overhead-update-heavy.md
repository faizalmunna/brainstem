---
name: elasticsearch-segment-merge-overhead-update-heavy
description: An update-heavy or upsert-heavy workload causes excessive segment merging that degrades both indexing throughput and query latency.
triggers: ["elasticsearch indexing slow under updates", "too many segments elasticsearch", "merge throttling elasticsearch", "update heavy workload slow search", "why does indexing throughput drop over time", "segment count growing"]
permissions: ["READ"]
---

## Symptom
An index that receives frequent updates (upserts to existing document
IDs, partial updates, or delete-then-reindex patterns) shows indexing
throughput and query latency both degrading over time under sustained
load, even though total document count isn't growing proportionally --
distinct from a purely append-only ingestion workload, which doesn't
exhibit the same pattern at similar volume.

## Likely causes
1. **Every update in Elasticsearch is internally a delete-plus-reindex**,
   not an in-place mutation -- the old document version is marked deleted
   in its existing segment (not physically removed) and a new version is
   written as a new document, so an update-heavy workload accumulates
   deleted-but-not-yet-purged documents inside segments far faster than
   an append-only workload would, and those deleted docs still consume
   segment space and get scanned during merges until reclaimed.
2. **A high indexing/refresh rate creates many small segments faster than
   the merge policy can consolidate them**, especially with a short
   `refresh_interval` (or the default 1s) under heavy write load --
   query time suffers because more segments means more per-segment work
   fanned out for every search, and merge activity competing for the
   same disk I/O and CPU as indexing further slows ingestion.
3. **Merge throttling is engaging** (Elasticsearch deliberately limits
   merge I/O to avoid starving search/indexing, especially relevant on
   slower disks) which is a real disk-I/O-driven cause the app team may
   misdiagnose as unrelated app-level slowness, since it doesn't show up
   as an explicit error, only as generally elevated latency.
4. **Routing/ID design causes non-uniform update distribution across
   shards** (a hot subset of document IDs updated far more often than
   others) concentrating delete/merge overhead onto specific shards
   rather than spreading it evenly, so cluster-wide averages look fine
   while a few shards are actually saturated.

## Diagnose
- Check `GET /<index>/_stats/merge` and `GET /<index>/_stats/segments`
  for segment count trending up and merge time/count accumulating faster
  than expected relative to indexing volume.
- Check `GET /<index>/_stats/docs` for `deleted` document count relative
  to `count` -- a high ratio of deleted-to-live documents confirms the
  update/delete-heavy pattern is leaving substantial reclaimable space
  unmerged.
- Check node-level I/O metrics (`GET _nodes/stats/fs`) and correlate
  spikes with merge activity timing to distinguish disk-I/O-bound merge
  throttling from unrelated causes (network, GC per
  `elasticsearch-jvm-heap-gc-pressure-from-aggregations`, query-side
  issues).
- Review the current `refresh_interval` setting
  (`GET /<index>/_settings`) and actual write pattern (batched bulk
  writes vs. many small individual update requests) to see whether
  refresh frequency is unnecessarily high for the actual near-real-time
  requirement.

## Fix
- Increase `refresh_interval` (e.g. from the 1s default to 30s or higher)
  for indices where near-real-time search isn't actually required at
  sub-second freshness, which reduces the rate of new small segment
  creation and gives the merge policy more headroom to consolidate
  efficiently.
- Batch updates into bulk requests rather than issuing many individual
  update API calls, reducing per-request overhead and giving
  Elasticsearch larger, more efficient units of work to index and merge.
- For workloads that are conceptually "replace this document's current
  state" rather than true incremental updates, consider whether the
  access pattern can tolerate eventual consistency via periodic full
  reindex/bulk-replace instead of continuous per-document updates, which
  avoids the ongoing delete-accumulation pattern entirely for that data.
- Tune `index.merge.policy` settings deliberately (e.g.
  `segments_per_tier`, `max_merged_segment`) only after confirming via
  the diagnostics above that default merge policy tuning, not disk I/O
  capacity, is the actual bottleneck -- and consider whether the
  underlying storage (especially spinning disk or throttled network
  storage) needs to be faster before tuning merge policy further.

## Pitfalls
- Disabling merge throttling (`index.store.throttle.type: none` or
  similarly aggressive merge policy changes) to "speed up" merging can
  starve concurrent search/indexing I/O instead, trading one latency
  problem for another rather than solving the root cause.
- Setting `refresh_interval` to `-1` (disabling automatic refresh
  entirely) to eliminate refresh overhead removes near-real-time search
  visibility entirely and requires an explicit refresh call to see new
  documents -- appropriate for bulk-load windows, not as a blanket
  production setting without confirming the app doesn't need timely
  visibility of writes.
- Force-merging a live, actively-written index
  (`POST /<index>/_forcemerge`) to immediately reclaim deleted-document
  space is I/O-intensive and can cause a significant temporary
  performance hit -- appropriate for indices that are done being written
  to (e.g. yesterday's rolled-over log index), not as a routine
  operation on a hot, actively-updated index.

## Verify
After the fix, confirm via `GET /<index>/_stats/docs` that the
deleted-to-live document ratio stabilizes rather than climbing
unbounded under continued load, confirm `GET /<index>/_stats/segments`
shows segment count staying in a reasonable steady-state range rather
than growing unbounded, and measure indexing throughput and query
p99 latency under sustained realistic load to confirm both have
recovered toward baseline.
