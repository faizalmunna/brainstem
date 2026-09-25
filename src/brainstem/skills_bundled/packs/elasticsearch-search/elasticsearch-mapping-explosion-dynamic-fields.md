---
name: elasticsearch-mapping-explosion-dynamic-fields
description: Dynamic mapping on a field holding arbitrary user-supplied keys creates thousands of unique mapped fields and destabilizes the cluster.
triggers: ["too many fields in mapping elasticsearch", "field limit exceeded", "mapping explosion", "cluster state too large", "indexing arbitrary json keys as fields", "Limit of total fields exceeded"]
permissions: ["READ"]
---

## Symptom
Indexing requests start failing with `Limit of total fields [1000] in
index [...] has been exceeded`, or cluster state size and master node
memory climb steadily over weeks with no corresponding growth in
document count, or `GET /<index>/_mapping` returns an enormous response
listing thousands of narrowly-specific field names that were never
explicitly designed.

## Likely causes
1. **A document field holds arbitrary, caller-controlled keys** (a
   `metadata`, `attributes`, `tags`, or `properties` object where each
   customer/event can introduce new key names) and dynamic mapping is
   left enabled, so every distinct key ever seen becomes a permanent,
   separate field in the mapping -- mappings can only grow, never shrink,
   for the life of the index.
2. **A single misbehaving producer sends a bug-generated unique key per
   event** (e.g. embedding a timestamp or request ID into a field name
   instead of a field value), which can generate thousands of new fields
   in a very short time window and is the fastest path to actually
   destabilizing a cluster, as opposed to a slow organic accumulation.
3. **Nested/object structures with dynamic mapping compound the problem
   multiplicatively** -- each new top-level dynamic key that itself
   contains a nested object multiplies into multiple new fields (one per
   leaf value), not just one.
4. **`index.mapping.total_fields.limit` was raised as a quick fix for the
   error** in the past without addressing the underlying dynamic-key
   pattern, deferring the cluster-state-size problem rather than
   resolving it, until it resurfaces at a larger scale.

## Diagnose
- Run `GET /<index>/_mapping` and check the response size and field
  count (`GET /<index>/_mapping | grep -o '"type"' | wc -l` as a rough
  proxy, or use `_field_caps` for an exact count) -- confirm actual field
  count against the configured `index.mapping.total_fields.limit`.
- Identify which top-level object is generating the most distinct fields
  by inspecting field name patterns in the mapping output -- a cluster of
  field names sharing a common prefix (e.g. `metadata.customer_field_*`)
  usually points to the exact offending document structure.
- Check recent ingestion logs/producers for a specific service or
  pipeline that started sending a new shape of document around the time
  field count began climbing -- correlate mapping growth rate
  (`GET /<index>/_mapping` field count sampled over time, or cluster
  state size in monitoring) against deploy history of ingestion services.
- Confirm whether `dynamic: true` (the default) is set on the offending
  object path specifically, via `GET /<index>/_mapping` showing
  `"dynamic"` settings at each object level.

## Fix
- Change the offending object's mapping to `"dynamic": "false"` (fields
  are still indexed in `_source` and retrievable, but not added to the
  mapping or made queryable/aggregatable as individual fields) if the
  arbitrary keys don't need to be individually searchable, or
  `"dynamic": "strict"` if unexpected fields should instead cause
  ingestion errors to surface the problem at the source.
- For arbitrary key-value data that genuinely needs to be queried, remodel
  it as the `flattened` field type (or `nested` with a fixed `key`/`value`
  field pair) instead of letting each distinct key become its own mapped
  field -- `flattened` indexes an entire object's contents as a single
  field's worth of mapping overhead, regardless of how many distinct keys
  appear inside it, trading per-key type-specific querying for a single
  bounded field.
- Set `index.mapping.total_fields.limit` back down to a deliberate value
  once the dynamic mapping is contained, so a future regression fails
  loudly and early rather than silently growing cluster state again.
- For a runaway producer bug (unique keys generated per event), fix the
  producer to stop encoding variable data into field *names*, and
  consider reindexing into a corrected mapping since the already-exploded
  mapping fields aren't automatically removed by fixing the producer
  going forward.

## Pitfalls
- Raising `index.mapping.total_fields.limit` as the fix (rather than
  containing the dynamic mapping) only delays the same cluster-state-size
  problem to a larger, harder-to-recover scale -- treat the limit as a
  circuit breaker to preserve, not an obstacle to raise.
- Switching to `flattened` after the fact doesn't retroactively shrink an
  already-bloated mapping on the existing index -- the index still needs
  reindexing into a new mapping to actually recover the cluster state
  size, changing the mapping setting alone only stops further growth.
- `flattened` fields support only limited query types (term-level
  queries, not full per-key numeric range/aggregation semantics per
  distinct key) -- confirm actual query requirements against
  `flattened`'s capabilities before adopting it as the fix, rather than
  discovering the gap after reindexing.

## Verify
After applying the mapping change and reindexing if needed, confirm
`GET /<index>/_mapping` field count has stopped growing under continued
normal ingestion (sample it before/after a period of live traffic), and
confirm cluster state size/master node heap usage (`GET
_cluster/state` size, `GET _nodes/stats`) has stabilized rather than
continuing to climb.
