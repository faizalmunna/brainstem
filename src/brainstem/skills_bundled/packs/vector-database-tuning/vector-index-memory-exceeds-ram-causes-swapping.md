---
name: vector-index-memory-exceeds-ram-causes-swapping
description: A vector index's in-memory footprint grows past available RAM at production scale, causing disk paging and a severe, sudden jump in query latency.
triggers: ["vector db query latency spiked suddenly", "vector index out of memory", "hnsw memory usage too high", "vector search node is swapping", "how much ram does my vector index need"]
permissions: ["READ"]
---

## Symptom
Query latency was stable for a long time and then degrades sharply -- not gradually -- often by an order of magnitude or more, frequently correlated with an ingest batch or a specific point in dataset growth rather than a code deploy. Host-level metrics (if available) show high swap usage, high disk I/O, or the process's resident memory approaching or exceeding the container/host memory limit around the same time. Unlike the gradual drift covered by the "index not retuned as dataset grows" skill, this failure is a comparatively sudden cliff-edge once memory crosses the available RAM boundary, because paging behavior is non-linear -- a small amount of overflow causes disproportionate slowdown since disk latency is orders of magnitude worse than RAM.

## Likely causes
1. HNSW's memory footprint per vector is dominated by the graph's neighbor links (proportional to `M`) plus the raw vector storage, and `M` (or the count of stored vectors) grew without anyone recalculating total memory need -- an `M` value increased earlier to improve recall directly multiplies memory per vector, and that cost wasn't budgeted against available RAM.
2. Full-precision (float32) vectors are stored when the workload could tolerate quantization -- product quantization (PQ), scalar quantization (SQ/int8), or binary quantization can cut memory by 4-32x with a measured, bounded recall cost, and this tradeoff was never evaluated before RAM became the constraint.
3. The deployment assumed the index would fit in RAM based on dataset size at launch, with no monitoring or alerting on memory headroom, so growth silently ate through the margin until the host started swapping with no advance warning.
4. Multiple collections/indexes (or multiple replicas of the same index for different environments) are co-located on the same host without accounting for their combined memory footprint, so per-index sizing looked fine in isolation but the host-level total wasn't checked.

## Diagnose
1. Pull host or container-level memory metrics (RSS, swap usage, page fault rate) for the vector DB process and correlate the latency spike timestamp directly against when RSS crossed the available memory limit -- this confirms paging as the mechanism rather than, e.g., a query pattern change.
2. Compute expected index memory footprint from the engine's documented formula (roughly, for HNSW: `N * (vector_dim * 4 bytes + M * 2 * ~8-12 bytes overhead)`) using current N, and compare against the host's actual available RAM, including headroom for the OS, other processes, and query-time working memory (not just the resident index).
3. Check whether quantization is currently enabled or disabled for this collection, and if disabled, estimate the memory savings quantization would provide against the measured shortfall.
4. Check for co-located collections/replicas on the same host and sum their footprints rather than evaluating this collection in isolation.

## Fix
Size the index against a memory budget explicitly, with headroom (a common rule of thumb is to budget for peak dataset size, not current size, plus enough slack for query-time overhead and OS/cache usage) rather than discovering the ceiling by hitting it in production. Where the full recall of float32 HNSW isn't required, adopt quantization (PQ/SQ/binary, or engine-native options like Qdrant's scalar/binary quantization or Milvus's IVF_PQ) as a deliberate, measured tradeoff -- benchmark the recall cost against the ground-truth set before rolling out, since quantization's recall impact varies by dataset and isn't free. For workloads that must stay full-precision, consider horizontal sharding (splitting the collection across multiple nodes, each independently sized to fit in RAM) rather than vertically scaling a single node indefinitely.

## Pitfalls
Don't apply quantization reactively during an active memory incident without first checking its recall impact against the ground-truth benchmark -- a memory fix that silently tanks recall trades one production incident for a quieter, harder-to-notice one. Also don't rely on the OS's swap as an implicit safety net "in case memory runs out" -- for a latency-sensitive query path, allowing swap to engage at all is already the incident; the fix is preventing memory pressure from reaching that point, not tolerating degraded performance once it does.

## Verify
After resizing, quantizing, or sharding, confirm resident memory stays below a defined threshold (e.g. 70-80% of available RAM) under peak load and under projected growth for the next planning period, and confirm via the recall@k benchmark that any quantization introduced stays within the application's acceptable recall loss (e.g. no more than a few percentage points off the pre-quantization baseline).
