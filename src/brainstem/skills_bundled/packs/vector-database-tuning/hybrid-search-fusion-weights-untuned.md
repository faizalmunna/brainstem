---
name: hybrid-search-fusion-weights-untuned
description: A hybrid search combining dense vector similarity with a sparse keyword score performs worse than either signal alone because the fusion weighting between them was never tuned.
triggers: ["hybrid search is worse than vector search alone", "combining bm25 and vector scores gives bad results", "reciprocal rank fusion weights", "hybrid search alpha parameter tuning", "keyword and vector search fusion ranking is off"]
permissions: ["READ"]
---

## Symptom
A collection supports both dense vector search and a sparse/keyword score (BM25, SPLADE, or the engine's native sparse index), and the hybrid combination -- meant to get the best of both -- underperforms running either the vector search alone or the keyword search alone on the same query set, measured by any relevance metric available (click-through, human judgment, or a retrieval eval). This is specifically about the score-combination step at the index/database query layer, not about whether to add a keyword component at all (that pipeline-level decision is covered by the RAG pack's own-keyword-match skill) -- here, both components already work individually, and the fusion is what's broken.

## Likely causes
1. Raw scores from the two systems are combined with a fixed linear weight (`alpha * vector_score + (1-alpha) * keyword_score`) that was set to a default (often 0.5) and never tuned against this collection's actual query and relevance distribution -- vector similarity scores and BM25 scores have different, non-comparable scales and distributions, so a naive linear blend at an untuned weight can let whichever score happens to have larger typical magnitude dominate regardless of the intended weight.
2. Reciprocal Rank Fusion (RRF) or another rank-based fusion method is used specifically to avoid the score-scale problem, but its constant (commonly `k=60` in the standard formula) or the underlying assumption that both rankers contribute equally-informative rankings was never validated for this specific corpus and query mix, where one signal may be systematically more reliable than the other.
3. The fusion weight was tuned once against a general or synthetic query set and never revisited as real query patterns diverged from that set -- e.g. a corpus that started mostly narrative text (where dense vectors dominate) later added structured/code content (where exact keyword match matters far more), shifting the optimal weight without anyone retuning it.
4. Fusion is applied uniformly across all query types when the optimal weighting is actually query-dependent -- short, keyword-heavy, entity-specific queries (product SKUs, error codes, proper nouns) benefit from weighting keyword score higher, while longer natural-language queries benefit from weighting vector score higher, and a single global weight is a compromise that's wrong for both extremes.

## Diagnose
1. Run the same evaluation query set through vector-only, keyword-only, and hybrid search and compare a relevance metric (nDCG, MRR, or recall@k against labeled relevant documents) across all three -- confirming hybrid actually underperforms the better of the two standalone methods (not just "feels off") is the necessary first step before touching fusion weights.
2. If using linear score combination, log and plot the raw score distributions from each component separately across a query sample -- if one component's scores span a much wider or narrower range than the other, that alone can explain a nominally-balanced weight producing an unbalanced actual influence.
3. Sweep the fusion weight (`alpha` for linear combination, or the RRF constant) across a range against the labeled evaluation set from step 1 and plot the relevance metric -- identify whether there's a clearly better weight than the current one, and how sensitive the metric is to the choice (a sharp optimum vs. a flat curve changes how much tuning effort is worthwhile).
4. Segment queries by type (short/entity-heavy vs. long/natural-language, or by any other available taxonomy) and check whether the optimal weight differs meaningfully by segment -- this reveals whether the real problem is a single wrong global weight or a genuinely query-dependent optimum that no single global weight can serve well.

## Fix
Normalize component scores to a comparable scale (e.g. min-max or z-score normalization within each query's result set) before applying a linear weight, or prefer a rank-based fusion method (RRF) specifically when raw score comparability is unreliable, and tune whichever method's parameter against a labeled relevance set for this corpus rather than a textbook default. If diagnosis shows a genuinely query-dependent optimum, implement query-type-aware weighting (a simple heuristic like query length/entity density, or a lightweight classifier) that selects or interpolates a fusion weight per query rather than forcing one global compromise value.

## Pitfalls
Don't tune the fusion weight against a single, small, hand-picked query set and assume it generalizes -- fusion weight optima are sensitive to the query mix, and a weight tuned on developer-written test queries often doesn't match real user query patterns, which tend to skew shorter and more varied. Also avoid re-tuning only when a regression is noticed rather than on a schedule tied to corpus or query-pattern change -- since (per cause 3) the optimal weight drifts as content mix shifts, treat it as a metric to periodically re-validate, not a constant set once at launch.

## Verify
Confirm the tuned (or query-type-aware) fusion configuration beats both standalone vector-only and keyword-only search on the labeled evaluation set by the chosen relevance metric, and re-check this comparison periodically (or after any significant shift in corpus composition or query patterns) rather than treating the initial tuning as permanent.
