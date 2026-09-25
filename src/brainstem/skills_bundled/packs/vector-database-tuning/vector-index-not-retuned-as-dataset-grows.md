---
name: vector-index-not-retuned-as-dataset-grows
description: A vector index built once at launch dataset size develops worsening latency or recall over months as the collection grows well past its original scale, without any config change.
triggers: ["vector search got slower over time", "index performance degraded after months in production", "do I need to rebuild my vector index periodically", "vector db worked fine at launch but is slow now", "recall dropped as we added more documents"]
permissions: ["READ"]
---

## Symptom
The vector index performed within SLO at launch and for a while afterward, then latency, recall, or both drifted noticeably worse over a period of weeks to months -- with no application code change, no query pattern change, and no single deploy that correlates with the regression. The only thing that changed continuously is dataset size (rows inserted daily). Looking at a latency or recall dashboard (if one exists) shows a slow, monotonic decline rather than a step change, which is the signature of parameters that were correct for the original N but not for the current N.

## Likely causes
1. Index-time parameters chosen for the original dataset size (HNSW's `M`/`ef_construction`, or IVF's `nlist`) were never revisited; as covered in the IVF-specific skill, `nlist` in particular becomes systematically wrong as N grows if left fixed, and HNSW's fixed `M` produces a progressively "thinner" relative connectivity graph as node count increases even though `M` per node stays constant.
2. The index was built with capacity/growth headroom assumptions baked in at creation time (e.g. a fixed pre-allocated size or shard count) that the dataset has now exceeded, forcing degraded fallback behavior (extra hops, overflow buckets, secondary structures) that wasn't present at smaller scale.
3. Incremental inserts into a graph-based index (HNSW) accumulate structural drift -- individual inserts are locally optimal but the graph as a whole slowly diverges from what a from-scratch build at the current N would produce, an effect sometimes called graph degradation, and it compounds silently because no single insert causes a visible regression.
4. Deletes are implemented as tombstones/soft-deletes rather than true removal (common in many vector DBs to avoid expensive graph surgery), so the effective working set the search traverses keeps growing even when the logical row count is stable, inflating latency without inflating any dashboard that only tracks live row count.

## Diagnose
1. Correlate a latency or recall timeseries against a raw row-count timeseries over the same window (pull both from the DB/collection stats and any APM data) -- a monotonic decline tracking row-count growth (not deploys, not traffic spikes) confirms scale drift rather than a regression from a code change.
2. Check the collection's tombstone/deleted-but-not-compacted count if the engine exposes it (Milvus segment stats, Qdrant's point count vs. indexed vector count, pgvector's dead tuple count via `pg_stat_user_tables`) -- a large gap between logical and physical vector count points to cause 4.
3. Re-run the same ground-truth recall@k measurement used at launch time (if it was captured then) against the current index and compare directly -- if no baseline was captured at launch, build one now and treat it as the new baseline going forward.
4. Compare current `nlist`/`M`/`ef_construction` against what the sizing heuristics recommend for the *current* row count (not the count at index creation) to quantify how far the live config has drifted from what a fresh build would choose.

## Fix
Schedule periodic index maintenance tied to relative growth, not a calendar date -- e.g. trigger a rebuild/retrain when row count crosses 3-5x the count at last build, rather than "every quarter," since a slow-growing collection doesn't need it and a fast-growing one needs it sooner. For engines that support it, prefer online/incremental re-optimization (Milvus segment compaction and index rebuild on merge, Qdrant's optimizer) over full rebuilds so this doesn't require downtime. Where soft-deletes are the mechanism, ensure compaction/vacuum is actually scheduled and running, not just theoretically available -- check the last successful compaction timestamp, not just that the feature exists.

## Pitfalls
Don't treat "the index still returns results within the timeout" as evidence nothing is wrong -- degradation here is gradual and recall-based, so a latency-only alert will miss the failure mode covered by the sibling "ANN recall tradeoff not measured in production" skill entirely; the two problems compound (an unmonitored, unretuned index is the worst combination). Also avoid full destructive rebuilds as a reflexive first response without checking whether the actual cause is stale IVF clustering (needs retraining), HNSW graph drift (needs rebuild), or tombstone bloat (needs compaction, which is far cheaper) -- they have different remedies and costs.

## Verify
After retuning/rebuilding, re-run the recall@k benchmark and confirm it returns to the original launch-time baseline (or the application's stated target), and set up a recurring job that reruns this same benchmark on a schedule (e.g. weekly) so the next drift is caught by a dashboard rather than a user complaint.
