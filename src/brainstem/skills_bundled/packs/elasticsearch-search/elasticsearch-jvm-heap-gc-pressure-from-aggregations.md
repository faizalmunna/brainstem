---
name: elasticsearch-jvm-heap-gc-pressure-from-aggregations
description: Search latency spikes and nodes become unresponsive from frequent long JVM garbage collection pauses driven by high-cardinality aggregation memory usage.
triggers: ["elasticsearch high heap usage", "long gc pauses elasticsearch", "circuit_breaking_exception data too large", "node unresponsive high cardinality aggregation", "search latency spikes gc", "fielddata circuit breaker"]
permissions: ["READ"]
---

## Symptom
Search and indexing latency intermittently spikes cluster-wide, node
logs show frequent or unusually long garbage collection pauses (visible
in GC logs or `GET _nodes/stats/jvm`), and in severe cases nodes drop out
of the cluster during a long GC pause (perceived as a node failure by
the rest of the cluster) or requests fail with
`circuit_breaking_exception`.

## Likely causes
1. **A `terms` or `cardinality` aggregation runs against a high-
   cardinality field** (user IDs, free-text-derived values, raw IPs) with
   a large or unbounded `size` parameter, forcing the node to hold a very
   large number of unique bucket values in heap simultaneously across
   shards during aggregation collection.
2. **Fielddata is enabled on a `text` field** (rather than aggregating on
   a `keyword` field/sub-field) -- fielddata loads all analyzed terms for
   a field into heap on first use and stays there, and on a high-
   cardinality analyzed text field this can consume enormous heap for a
   query pattern that should have used doc-value-backed `keyword`
   aggregation instead.
3. **The circuit breaker limits are set too high, or disabled, relative
   to actual available heap**, so requests that should be rejected early
   (protecting node stability) are instead allowed to proceed until they
   actually exhaust heap and trigger a long GC pause or `OutOfMemoryError`
   rather than a clean, fast rejection.
4. **General heap sizing is too small for the actual working set** (heap
   set well below the recommended ~50% of available RAM, or below the
   actual aggregation/cache working set the workload requires), so normal
   query patterns that would be fine on a correctly-sized node
   consistently push into GC pressure.

## Diagnose
- Check `GET _nodes/stats/jvm?filter_path=**.gc` for `collection_time`
  and `collection_count` on the old-generation collector trending up
  sharply, correlated with the timing of the latency spikes.
- Check node logs for `circuit_breaking_exception` messages, which name
  the specific breaker tripped (`fielddata`, `request`, `parent`) --
  this points directly at which memory consumer is the problem rather
  than requiring broad GC-log archaeology.
- Run the suspected aggregation query with `"profile": true` and inspect
  memory-relevant details, and check `GET _nodes/stats/indices/fielddata`
  for fielddata memory usage per node, and `GET _cat/fielddata?v` to see
  which specific fields are consuming fielddata heap.
- Review slow logs and recent dashboard/query changes for a `terms`
  aggregation with a large `size` on a field later confirmed
  high-cardinality via `GET /<index>/_search` with a `cardinality`
  aggregation on that field.

## Fix
- Aggregate on `keyword` fields (doc-value-backed, not loaded fully into
  heap the way fielddata is) rather than enabling fielddata on `text`
  fields -- if text search and aggregation are both needed on the same
  content, use a `text` field with a `keyword` multi-field and aggregate
  on the `.keyword` sub-field specifically.
- Bound aggregation `size` to what's actually needed for the use case
  (top-N reporting rarely needs more than dozens to low hundreds of
  buckets) rather than requesting a very large or default-unbounded
  bucket count on a high-cardinality field; for approximate distinct-
  count needs, use the `cardinality` aggregation (which uses a bounded-
  memory HyperLogLog++ algorithm) instead of a `terms` aggregation sized
  to try to enumerate every unique value.
- Leave circuit breaker limits (`indices.breaker.*`) at or near their
  defaults relative to configured heap rather than raising them to make
  errors "go away" -- a request rejected by the circuit breaker is a
  fast, recoverable failure; a request that exhausts heap and triggers
  a long GC pause or crash is a much worse outcome for the whole node.
- Size heap according to standard guidance (roughly 50% of available RAM,
  capped comfortably under 32GB to stay under the compressed-ordinary-
  object-pointer limit) and validate against the workload's actual
  aggregation/cache memory needs rather than a value chosen without
  reference to real usage.

## Pitfalls
- Raising circuit breaker limits (or disabling them) to eliminate
  `circuit_breaking_exception` errors removes the node's early-warning
  protection and trades a fast, clean rejection for the risk of a slow
  GC-pressure death spiral or node crash under the same load.
- Setting heap above roughly 32GB (crossing the JVM's compressed-
  ordinary-object-pointer threshold) increases effective per-object
  memory overhead and can perform worse than a smaller heap below that
  threshold -- more heap is not unconditionally better.
- Adding more heap to "fix" a fielddata-on-text-field misconfiguration
  treats the symptom, not the cause -- the same query pattern will
  eventually outgrow any heap size as data volume/cardinality grows;
  fixing the aggregation target field is the durable fix.

## Verify
After the fix, re-run the previously problematic aggregation and confirm
via `GET _nodes/stats/jvm` that old-generation GC frequency/duration
during that query returns to baseline, confirm `GET _cat/fielddata?v`
shows no unexpected fielddata usage on the field in question, and monitor
for a sustained period to confirm `circuit_breaking_exception` no longer
occurs under normal peak load.
