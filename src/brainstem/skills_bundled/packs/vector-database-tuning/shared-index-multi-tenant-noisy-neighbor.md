---
name: shared-index-multi-tenant-noisy-neighbor
description: One tenant's large or high-traffic vector collection degrades query performance for other, smaller tenants sharing the same underlying vector index or cluster.
triggers: ["one customer's data is slowing down everyone else's search", "multi-tenant vector db noisy neighbor", "small tenant has slow vector search on shared index", "how to isolate tenants in a vector database", "tenant filter on shared vector index is slow"]
permissions: ["READ"]
---

## Symptom
Small tenants experience inconsistent or degraded query latency that doesn't correlate with their own data volume or query rate at all -- it correlates with a different, much larger tenant's activity (bulk ingests, high query volume, or simply that tenant's total row count) on the same shared collection or cluster. Sizing a small tenant's own workload in isolation would predict fast queries; the actual behavior only makes sense once the shared index's total scale (dominated by the largest tenant) is factored in.

## Likely causes
1. Tenant isolation is implemented purely as a metadata filter (`tenant_id = X`) over one shared index rather than physically or logically separate indexes -- this hits the filtered-ANN-search problem directly: a small tenant's query becomes a highly selective filter over a graph/cluster structure sized and shaped by the dominant tenant's data, and traversal cost is driven by the shared structure's total size, not the small tenant's slice of it.
2. A large tenant's bulk ingest or reindex job runs against the same shared index/cluster resources (CPU, memory bandwidth, I/O) that small tenants' queries depend on, with no resource isolation (no separate collection, no rate limiting, no separate compute) between ingest and query workloads across tenants.
3. IVF-style clustering was trained on the overall dataset dominated by the largest tenant's vector distribution, so cluster boundaries are optimized for that tenant's data shape and are a poor fit for a smaller tenant's differently-distributed vectors, degrading that tenant's recall/latency tradeoff specifically.
4. Per-tenant quotas or resource limits don't exist at all -- the system was designed and tested with same-sized synthetic tenants, so the failure mode of one wildly disproportionate tenant was never exercised before production traffic revealed it.

## Diagnose
1. Correlate a small tenant's query latency timeseries against total collection size and against specifically the largest tenant's row count/query rate over the same window, not against the affected tenant's own metrics -- a correlation with someone else's numbers confirms cross-tenant interference.
2. Check the isolation architecture directly: is each tenant a separate collection/index (physical isolation), a separate partition/segment within one collection (partial isolation, e.g. Milvus partitions or Qdrant's payload-based sharding), or purely a metadata filter over one flat index (no structural isolation)? This determines which fix applies.
3. During a known large-tenant bulk ingest window, measure other tenants' query latency directly to confirm ingest-vs-query resource contention as a distinct mechanism from index-structure sharing.
4. If using IVF, check recall@k specifically for a small tenant's queries against ground truth restricted to that tenant's own vectors -- a gap here versus the dataset-wide recall number points to cluster-shape mismatch (cause 3) rather than pure resource contention.

## Fix
Prefer structural isolation over filter-based isolation once tenant size variance is significant: separate collections per tenant (or per tenant tier) give each tenant an index sized and shaped for its own data, eliminating both the filtered-search penalty and the cross-tenant cluster-shape mismatch. Where full per-tenant collections aren't practical (e.g. very many small tenants), use the engine's native partitioning primitive (not a bare metadata filter) so the engine can route a tenant's query to only its own partition's graph/cluster structure rather than traversing a shared one and filtering after the fact. Separate ingest and query resource paths for large tenants (dedicated ingest workers, rate limiting, or off-peak scheduling for bulk loads) so one tenant's write-heavy workload doesn't starve others' read-heavy workload on shared compute.

## Pitfalls
Don't solve this purely by adding a payload index on `tenant_id` and calling it done -- a scalar index speeds up the filter evaluation itself but doesn't change the fact that the underlying ANN structure (the graph or clusters) may still be shaped by and sized for the dominant tenant, which is a structural problem a faster filter doesn't fix. Also avoid over-correcting into fully isolated per-tenant infrastructure for every tenant regardless of size, which can multiply operational overhead (many tiny indexes to monitor and maintain) disproportionately to the actual noisy-neighbor risk for genuinely small, low-traffic tenants -- reserve full isolation for tenants above a measured size/traffic threshold.

## Verify
After introducing partitioning or isolation, re-run the correlation check from Diagnose step 1 across a window that includes a large tenant's peak ingest or query activity, and confirm small tenants' latency no longer moves with the large tenant's activity; separately confirm the small tenant's recall@k now matches what a standalone index sized for that tenant alone would produce.
