---
name: hnsw-ef-search-too-low-hurts-recall
description: An HNSW index returns visibly wrong or missing nearest neighbors because ef_search (or the equivalent recall-tuning parameter) was set low to chase latency.
triggers: ["hnsw recall is bad", "vector search misses obviously relevant results", "ef_search tuning", "increasing ef_search fixes accuracy but slows queries", "why does my vector db return irrelevant top results"]
permissions: ["READ"]
---

## Symptom
Query latency on the vector index looks great (single-digit milliseconds), but the top-k results are visibly wrong: known-relevant items rank outside the top 10, or manually verified nearest neighbors (computed via brute-force cosine distance) don't appear at all. The gap between "index says these are nearest" and "brute-force says these are nearest" is large and doesn't close with more data cleanup, better embeddings, or query rewriting -- because the bottleneck isn't relevance, it's the approximate search itself under-exploring the graph.

## Likely causes
1. `ef_search` (Milvus/Qdrant/Weaviate) or `efSearch` (hnswlib/pgvector `hnsw.ef_search`) is set at or near its floor (e.g. 10-40) because a load test optimized purely for p99 latency without ever measuring recall against a ground-truth set.
2. The default was never touched at all -- many client libraries ship a low default (e.g. 40-64) intended for small toy indexes, and it was never revisited when the collection grew to millions of vectors, where the same ef_search yields much worse recall.
3. `ef_search` is set reasonably but is lower than `k` (the number of results requested) or close to it -- HNSW requires ef_search >= k, and values only slightly above k give the graph almost no room to correct greedy-search wrong turns.
4. The confusion is with build-time parameters (`ef_construction`, `M`) instead of the query-time knob -- someone tuned the wrong parameter, so query-time recall never moved regardless of how many times it was "fixed."

## Diagnose
1. Build a ground-truth set: pick 50-100 representative query vectors and compute their true top-k via exact brute-force distance (e.g. `numpy`/`faiss.IndexFlatL2`) over the same dataset.
2. Run the same queries through the live HNSW index and compute recall@k = |approx_topk ∩ true_topk| / k, averaged across the sample.
3. Sweep `ef_search` across a range (e.g. 32, 64, 128, 256, 512) against that same ground-truth set and plot recall vs. p50/p99 latency -- this reveals where the current setting sits on the curve and whether the app is trading away recall it doesn't need to.
4. Confirm which parameter is actually in play: check the collection/index config for `ef_construction`/`M` (build-time, fixed at index build) vs. `ef_search`/`ef` (query-time, adjustable without rebuilding) -- most engines expose these as separate settings, and it's a common mixup.

## Fix
Treat `ef_search` as a live, per-query-workload knob rather than a one-time default, and pick it from the measured recall/latency curve, not by lowering it until latency graphs look good. If the application has a hard SLO (e.g. p99 < 50ms), find the highest `ef_search` that satisfies it on the recall curve rather than the lowest value that "seems to work" on spot checks. Many engines (Qdrant, Milvus, Weaviate) allow setting `ef_search` per-query, so latency-sensitive paths (autocomplete) and quality-sensitive paths (RAG retrieval feeding an LLM) can use different values against the same index instead of one global compromise.

## Pitfalls
Don't raise `ef_search` to a very large value "to be safe" without re-measuring latency -- recall gains flatten out well before ef_search reaches dataset size, while latency keeps climbing roughly linearly, so past the knee of the curve it's pure waste. Also avoid conflating `ef_search` with `ef_construction`: raising `ef_construction` and rebuilding the whole index is expensive and only improves the graph's structural quality, it does nothing for a query-time recall problem that a config change could fix in seconds.

## Verify
Re-run the recall@k measurement from Diagnose step 1-2 after the change and confirm recall crosses the application's target threshold (e.g. recall@10 >= 0.95) while p99 latency stays within the stated SLO; keep the ground-truth script so this check can be repeated whenever the dataset grows significantly.
