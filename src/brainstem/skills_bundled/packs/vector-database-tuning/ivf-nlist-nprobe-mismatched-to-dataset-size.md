---
name: ivf-nlist-nprobe-mismatched-to-dataset-size
description: An IVF index's cluster count nlist and probe count nprobe were chosen without regard to actual dataset size, wasting resources on a small collection or losing recall on a large one.
triggers: ["ivf index recall is poor", "nlist nprobe tuning", "how many clusters for ivf index", "faiss ivf index is slow to build", "vector index recall drops after ingesting more data"]
permissions: ["READ"]
---

## Symptom
Two distinct failure shapes show up under this same root cause. On a small collection (tens of thousands of vectors), index build time and memory are surprisingly high, and query recall is oddly inconsistent, because `nlist` was set to a value meant for a much larger corpus (e.g. 16384 clusters for 50k vectors), leaving most clusters nearly empty. On a large, growing collection (tens of millions of vectors), recall silently degrades even though `nlist` looked reasonable at launch, because `nprobe` (the number of clusters searched per query) was never increased to match, so an ever-smaller fraction of the index is actually examined per query as the collection grows.

## Likely causes
1. `nlist` was copied from a tutorial or another team's config without recomputing it for this dataset's actual size -- the common guidance is `nlist ~= sqrt(N)` to a few times `sqrt(N)`, and using a fixed large constant regardless of N either starves small collections of training data per cluster or, for very large N, under-clusters.
2. `nprobe` was set once at initial dataset size and never revisited -- as N grows with `nlist` fixed, each cluster holds more vectors, so a fixed `nprobe` searches a shrinking fraction of the space and recall degrades gradually and silently.
3. The IVF index (or IVF+PQ) was trained (k-means clustering step) on too small or unrepresentative a sample of the data, so cluster boundaries don't reflect the actual vector distribution, and no amount of `nprobe` tuning fully compensates.
4. Confusing `nlist`/`nprobe` (IVF-family) tuning with `ef_search`/`M` (HNSW) tuning when a migration between index types happened but the old mental model (and old parameter values) carried over unchanged.

## Diagnose
1. Compute the actual vector count N and compare `nlist` against the `sqrt(N)`-to-`4*sqrt(N)` heuristic range -- an `nlist` far outside that range for the current N is the first red flag, in either direction.
2. Measure average vectors-per-cluster (`N / nlist`); clusters averaging under ~30-50 vectors indicate over-clustering for the data volume, which wastes memory on cluster metadata and centroids without meaningfully improving search granularity.
3. Build a ground-truth top-k set via brute-force search (same approach as HNSW recall testing) and measure recall@k at the current `nprobe`, then sweep `nprobe` upward (e.g. 1, 4, 16, 64) to see where recall plateaus -- if the plateau requires searching a large fraction of `nlist`, the clustering itself (not just `nprobe`) is likely too coarse.
4. Check when the index was last rebuilt/retrained versus current row count -- if the collection has grown 5-10x since the last `nlist` choice, that alone explains degraded recall at a fixed `nprobe`.

## Fix
Recompute `nlist` from current (or realistically projected near-term) dataset size using the `sqrt(N)` family of heuristics, and set `nprobe` from the measured recall/latency sweep rather than a fixed rule of thumb -- typically `nprobe` in the range of 1-10% of `nlist` is a reasonable starting search space, then adjust from the actual recall curve. For datasets expected to grow substantially, prefer scheduling periodic re-clustering (retraining the IVF quantizer) over a fixed initial choice, since IVF's cluster assignment quality (unlike HNSW's incrementally-extensible graph) degrades more directly as the trained distribution drifts from the live distribution.

## Pitfalls
Don't tune `nprobe` up indefinitely to chase recall without checking `nlist` first -- if the clustering itself is poor (too coarse or trained on stale data), even `nprobe = nlist` (an exhaustive scan of all clusters, at which point IVF provides no speed benefit at all) may not match a well-clustered index's recall at a fraction of the search cost. Also avoid rebuilding the whole index reactively only after a recall complaint; because IVF training assumes a representative sample, sudden distributional shifts (e.g. a new content category added to a shared embedding index) can silently invalidate cluster quality well before raw growth in N does.

## Verify
After adjusting `nlist`/`nprobe` (and retraining if clustering was stale), re-run the brute-force recall@k comparison from Diagnose step 3 and confirm recall meets the application's target at the chosen `nprobe`, and separately confirm average vectors-per-cluster falls in a healthy range (roughly 100s to low 1000s, not single digits and not hundreds of thousands).
