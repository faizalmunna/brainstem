---
name: ann-recall-not-monitored-in-production
description: A vector search system has no ongoing recall measurement in production, so a configuration or data change silently degrades result quality with no alert firing.
triggers: ["how do I monitor vector search quality", "no alerts fired but search results got worse", "measure ann recall in production", "vector db observability", "how do we know if the vector index is still accurate"]
permissions: ["READ"]
---

## Symptom
Every existing dashboard (query latency, QPS, error rate, index size) is green, yet users or downstream evaluation (e.g. a RAG answer-quality eval) report that search results have gotten worse over time. There is no metric anywhere in the stack that answers "is the ANN index still finding the true nearest neighbors," because recall is fundamentally a property that requires a ground-truth comparison to measure, and nothing in standard infra monitoring (which watches latency/throughput/errors) computes that comparison on its own.

## Likely causes
1. Recall was measured once, during initial index selection/benchmarking, and treated as a one-time signoff rather than an operational metric -- so the number that justified going to production drifts out of date the moment the config or dataset changes.
2. The team conflates "the search returns results without erroring" with "the search returns good results" -- these are orthogonal; an ANN index with terrible recall still returns a full, fast, error-free result set, just the wrong one.
3. There's no readily available ground-truth to compare against, because computing exact nearest-neighbors (brute-force) at production data volume is itself expensive, so it was deprioritized rather than run on a sample.
4. Recall regressions get attributed to the wrong layer -- blamed on "the embedding model" or "the LLM" (per the RAG-pipeline-level debugging skills) when the actual cause is index-layer drift (stale IVF clusters, un-retuned ef_search, growth past original sizing), because no metric isolates the index layer specifically.

## Diagnose
1. Check whether any existing metric or eval pipeline computes recall@k against a brute-force baseline at any cadence -- if the honest answer is "we checked once during the POC," that confirms the gap.
2. If a RAG quality eval exists (answer correctness, groundedness), check whether it can distinguish "retrieval found the right chunk but generation used it badly" from "retrieval didn't find the right chunk" -- if not, a real index-layer recall regression is invisible inside an end-to-end score that also depends on the LLM.
3. Pull a small (e.g. 100-500 vector) representative sample of production queries or corpus vectors and compute brute-force top-k for them offline, to establish feasibility and a first baseline number, even before building automation.
4. Check index config change history (if tracked) against any known quality complaints to see whether recall would plausibly explain them -- an `ef_search` lowered during a latency incident, an `nprobe` never adjusted after a growth milestone, etc.

## Fix
Stand up a recurring recall benchmark job, separate from end-to-end RAG/LLM evals, that: samples a fixed or rotating set of query vectors, computes brute-force ground truth on a matching data snapshot (or a representative subsample if full brute-force is too costly at scale), runs the same queries through the live ANN index, computes recall@k, and emits it as a first-class metric (e.g. to the same metrics backend as latency/QPS) with an alert threshold. Run it on a cadence tied to both time (e.g. daily) and data-change events (after large ingests, after any index config change, after a reindex), since either can independently cause drift. Keep this metric owned at the index/database layer, distinct from downstream RAG answer-quality metrics, so a regression can be localized to "the index" rather than requiring a full pipeline investigation every time.

## Pitfalls
Don't use a single global recall number as the only signal -- recall can vary substantially across query types (e.g. queries near cluster boundaries vs. cluster centers, or high- vs. low-selectivity filtered queries), so an aggregate can look fine while a specific important slice (a particular tenant, a particular filter combination) has silently degraded; segment the metric where practical. Also avoid computing the brute-force baseline once and reusing it forever as "ground truth" without refreshing it as the underlying data changes -- stale ground truth produces a recall number that looks stable while actually just being wrong in a consistent way.

## Verify
Confirm the recall benchmark job has run successfully at least twice on schedule (not just manually invoked once), that its output is visible on the same dashboard/alerting surface as other index health metrics, and that deliberately lowering a recall-affecting parameter (e.g. `ef_search`) in a staging environment produces a visible drop in the metric -- proving the instrumentation actually detects real regressions rather than just reporting a static number.
