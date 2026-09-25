---
name: wrong-index-type-chosen-for-workload
description: A vector database was configured with an index type, such as flat, IVF, or HNSW, that does not match the collection's actual size, update frequency, or latency requirements.
triggers: ["should I use hnsw or ivf", "which vector index type should I choose", "flat index vs approximate index", "vector index choice for small dataset", "high insert rate vector index keeps rebuilding"]
permissions: ["READ"]
---

## Symptom
The index "works" in the sense that it returns results, but something about its cost profile is clearly mismatched to the workload: a small collection (a few thousand to low tens of thousands of vectors) pays real operational complexity and approximation error for an ANN index when brute-force exact search would be both fast enough and exact; or, conversely, a write-heavy collection with frequent inserts/updates constantly pays expensive index-rebuild or re-balancing cost because the chosen index type doesn't support efficient incremental updates; or a latency-critical, read-heavy, rarely-updated collection uses an index type suited for the opposite profile and pays unnecessary complexity or recall loss for no benefit.

## Likely causes
1. An ANN index (HNSW or IVF) was adopted by default/convention for a collection small enough that exact brute-force search (a flat index) would meet latency requirements with zero approximation error and none of the tuning burden covered by the rest of this pack -- the decision to go approximate was never actually justified by a measured latency need.
2. HNSW was chosen for a workload with a very high insert/delete rate, where each insertion requires graph-search-based placement -- at high write throughput this becomes a bottleneck, and frequent deletes (handled as tombstones in most implementations) accumulate the graph-degradation and bloat issues covered elsewhere in this pack faster than a read-heavy workload would experience them.
3. IVF was chosen for a workload where the data distribution shifts frequently (e.g. streaming new topics/categories continuously), which requires frequent quantizer retraining to keep cluster boundaries meaningful -- a cost that wasn't factored into the original index choice.
4. The index type was copied from a tutorial, another team's default, or the vector DB's out-of-the-box default configuration without evaluating it against this workload's actual read/write ratio, latency requirement, and dataset size -- a decision made once for convenience rather than fit.

## Diagnose
1. Establish the actual dataset size and its growth trajectory, and the actual read/write ratio (queries per second vs. inserts/updates/deletes per second) -- these two numbers alone rule out several mismatches immediately (e.g. small + read-heavy strongly favors flat; large + write-heavy strongly disfavors naive HNSW).
2. Benchmark brute-force (flat) search latency directly against the current dataset size and the application's SLO -- if flat search already meets the SLO, the complexity and recall risk of an ANN index is pure overhead with no offsetting benefit, regardless of which ANN type is in use.
3. Measure current insertion/update throughput and its cost (time per insert, impact on concurrent query latency during heavy write periods) -- a rising per-insert cost as the graph/index grows, or visible query latency degradation during bulk writes, indicates a write-path mismatch.
4. Check how often the underlying data distribution meaningfully shifts (new categories, new languages, a different content type added) versus how often the index type in use requires full retraining/rebuilding to handle such shifts well.

## Fix
Choose the index type from measured workload characteristics, not convention: flat/brute-force for collections small enough that it meets latency SLOs (there's no recall tradeoff to manage, no tuning surface, and no ongoing maintenance burden -- often the right choice up to the tens-of-thousands-to-low-millions range depending on vector dimensionality and hardware); HNSW for read-heavy, moderate-write workloads needing strong recall at low latency; IVF (or IVF+PQ for memory-constrained cases) for very large, relatively static or batch-updated datasets where periodic retraining is acceptable; and consider engines/index types built specifically for high-write-throughput scenarios (e.g. DiskANN-style or LSM-tree-backed vector indexes) when write rate is the dominant constraint rather than trying to force HNSW or IVF into that role. Revisit the choice explicitly whenever dataset size crosses an order of magnitude or the read/write ratio shifts significantly, rather than treating the initial choice as permanent infrastructure.

## Pitfalls
Don't assume "approximate" is always the sophisticated/correct choice and "flat" is naive -- for small-to-moderate datasets, flat search is frequently the objectively better engineering choice (exact, no tuning surface, no recall monitoring burden), and reaching for ANN by default is itself a form of premature optimization. Also don't switch index types reactively mid-incident without benchmarking the replacement against this workload's actual read/write profile first -- swapping from one poorly-fitted index type to another popular one without measurement just relocates the mismatch.

## Verify
Benchmark the chosen index type against the application's actual SLOs for both query latency (via the recall@k-vs-latency methodology used elsewhere in this pack) and write throughput (inserts/sec without unacceptable query latency degradation) under realistic concurrent load, and document the workload assumptions (size, growth rate, read/write ratio) the choice was based on so a future reviewer can tell when those assumptions have changed enough to warrant revisiting it.
