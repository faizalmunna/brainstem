---
name: filtered-vector-search-collapses-performance
description: Combining a metadata filter with an ANN vector search is dramatically slower than either the filter or the vector search run alone.
triggers: ["filtered vector search is slow", "adding a where clause kills my vector search performance", "pre-filtering vs post-filtering ANN", "metadata filter plus similarity search timeout", "vector search returns too few results after filtering"]
permissions: ["READ"]
---

## Symptom
A pure top-k vector search over the collection returns in 5-10ms. A metadata-only filter (e.g. `tenant_id = X`) also returns fast. But `WHERE tenant_id = X ORDER BY vector <-> query LIMIT 10` (or the equivalent filtered ANN call) takes hundreds of milliseconds to seconds, or -- worse -- returns fewer than `k` results even though far more than `k` rows match the filter, because the ANN graph traversal exhausted its candidate budget before finding enough filter-matching neighbors.

## Likely causes
1. The engine implements **post-filtering**: it runs the ANN search first to get the top-N approximate neighbors, then discards any that fail the metadata filter -- if the filter is selective (matches a small fraction of the collection) and the true nearest neighbors happen to fail it, the result set is thin or empty, and the engine has to keep re-expanding the search (or simply can't) to compensate.
2. The engine implements **pre-filtering**: it evaluates the metadata predicate first to build an allowed-ID bitset, then restricts the graph traversal to only those IDs -- on a highly selective filter this turns HNSW's efficient graph-hopping into something close to a brute-force scan over a scattered subset, because the graph's neighbor links mostly point to now-excluded nodes.
3. The metadata field being filtered on has no index of its own (no B-tree/bitmap on the scalar column), so the filter step itself is a full scan that dominates the query, independent of the vector search cost.
4. The filter selectivity is being ignored -- the same query plan (pre-filter vs. post-filter, same `ef_search`) is used regardless of whether the filter matches 90% or 0.1% of rows, when the two cases need different strategies entirely.

## Diagnose
1. Time the three queries separately: vector-only top-k, filter-only (metadata predicate, no vector), and combined -- if combined time is much greater than the sum of the two, it confirms the interaction, not either component alone, is the problem.
2. Check the returned result count for the combined query against `k` -- fewer results than requested despite the filter matching many rows is the signature of an under-provisioned post-filter search (see cause 1).
3. Check the engine's docs/config for its filtering strategy name (Qdrant: pre-filtering with payload index; Milvus: scalar filtering + iterative search; pgvector: relies on Postgres planner choosing index scan vs. seq scan; Weaviate: pre-filtering with roaring bitmaps) -- confirm which mode is active for this collection, since some engines auto-switch based on estimated selectivity and some don't.
4. Compute filter selectivity directly: `count(*) where filter` / `count(*) total` -- selectivity below ~1% is where naive pre-filtering degrades hardest, and where post-filtering needs a much larger candidate pool.
5. For pgvector specifically, run `EXPLAIN ANALYZE` on the combined query and check whether Postgres chose a sequential scan instead of the HNSW/IVFFlat index -- the planner sometimes deprioritizes the vector index when a selective filter looks cheaper to satisfy first.

## Fix
Match the filtering strategy to measured selectivity rather than using one strategy everywhere. For low-selectivity filters (matches most of the collection), pre-filter to a bitset and let ANN search operate on the reduced set. For high-selectivity filters (matches a small fraction), either increase the ANN candidate pool substantially (raise `ef_search`/equivalent so the traversal has enough budget to find filter-passing neighbors) or use the engine's native filtered-search primitive if it has one (Qdrant's filterable HNSW, Milvus's iterative filtering, Elasticsearch/OpenSearch's pre-filter-then-kNN) instead of a generic "search then filter" client-side composition. Always add a scalar index (B-tree, bitmap, or the engine's payload index) on filtered fields so the filter itself isn't a bottleneck independent of the vector search.

## Pitfalls
Don't "fix" this by requesting a much larger `k` and filtering client-side down to the desired count -- it masks the symptom, wastes bandwidth and CPU on discarded candidates, and still silently fails once the filter is selective enough that even the larger k doesn't contain enough matches. Also avoid assuming one collection-wide filtering mode is correct forever: a filter's selectivity can shift as data grows (a tenant that was 30% of the collection can become 1% as other tenants onboard), silently moving the query into the bad regime without any code change.

## Verify
Re-run the combined filtered-vector query against a fixed test set spanning both high- and low-selectivity filter values, confirm it returns the full requested `k` results (or a documented reason for fewer), and confirm its latency stays within a small constant factor (not orders of magnitude) of the slower of the two standalone queries.
