---
name: caching-computed-result-with-volatile-inputs-poor-hit-rate
description: A cache was placed around a computed or aggregated result that depends on several frequently-changing inputs, so the cache key almost never matches a prior request and hit rate stays poor despite the caching effort.
triggers: ["we added a cache but hit rate is still terrible", "caching this endpoint didn't help at all", "cache key is basically unique every time", "computed result keeps missing the cache because inputs keep changing"]
permissions: ["READ"]
---

## Symptom
A cache was deliberately added around an expensive computation — a personalized ranking, a dashboard aggregate, a search-results page with many filters — but hit-rate metrics stay low (often single digits) no matter how the TTL is tuned. The team keeps adjusting TTL or cache size expecting it to help, but the real problem is structural: the cache key, built from the computation's inputs, is different on nearly every request because at least one of those inputs (a timestamp, a frequently-updated counter, a highly granular filter combination) changes too often for keys to ever repeat.

## Likely causes
1. **The cache key includes a naturally high-cardinality or continuously-changing input** — a "last updated" timestamp, a live inventory count, a per-request nonce or session ID that was included in the key without realizing it defeats reuse — so effectively every request looks unique to the cache even though the underlying business question is often the same.
2. **The computation combines a stable, cacheable part with a volatile part in a single cached unit** — e.g., a dashboard combines a slow-changing aggregate with a live "last active" timestamp, and caching the whole rendered result together means the volatile field's change rate governs the whole cache's effective hit rate.
3. **Caching was applied at the outermost layer (the full endpoint response) instead of at the layer where reuse actually exists** — many different top-level requests may share an expensive sub-computation (e.g., a common filter's result set) even though the full combined response is unique to each request.
4. **Personalization is baked into the cached unit** when only a small part of the result is actually personalized, so a mostly-shared computation gets a cache key scoped per-user and never benefits from cross-user reuse.
5. **Filter/parameter combinations are high-cardinality by nature** (many optional filters, free-text search, arbitrary sort orders) so the space of possible cache keys is enormous relative to how often any specific combination repeats, meaning even a "correct" cache design has an inherent ceiling on achievable hit rate for that granularity.

## Diagnose
1. Log the actual cache key being generated for a sample of real requests and check its cardinality — count how many distinct keys appear versus how many total requests, and inspect a few keys directly to spot an unexpectedly volatile component (timestamp, counter, nonce) that shouldn't be there.
2. For each input that feeds the cache key, separately determine its actual rate of change and cardinality — this identifies exactly which input is driving the poor hit rate rather than treating "hit rate is low" as one undifferentiated problem.
3. Decompose the computation on paper: which parts of the result are shared across many requests (stable, high-reuse) and which are unique per request (volatile, low-reuse)? A poor hit rate on the whole is often a good hit rate on the shared part diluted by a volatile part bundled into the same cache entry.
4. Check whether the volatile input actually needs to be exact/live in this context, or whether it could be bucketed (rounded to the nearest minute, rounded inventory ranges like "in stock" vs. an exact count) without harming the product requirement — this reveals whether the fix is architectural (split caching) or just over-precision in the key.

## Fix
Split the computation so the stable, high-reuse part is cached separately from the volatile part, and combine them at request time — cache the expensive shared aggregate under a key built only from its actual stable inputs, then merge in the volatile piece (fetched fresh or from a much-shorter-TTL cache) after the cache lookup, rather than caching the fully-assembled response as one unit. Where an input is volatile but doesn't need to be exact for the cached use case, bucket or round it (time-bucketed to the nearest N minutes, quantized counts) to deliberately increase key reuse without meaningfully harming correctness for that use case. Where personalization only affects a small slice of an otherwise-shared result, cache the shared slice unscoped and apply the personalized slice on top per-request instead of scoping the whole cache entry per-user.

## Pitfalls
Don't respond to a low hit rate by simply removing the volatile input from the key without checking whether it actually needs to affect the response — that "fixes" the hit rate by serving a wrong or stale-in-a-new-way result (silently ignoring a filter or personalization dimension that mattered), trading a performance problem for a correctness one. Also don't assume splitting the cache into stable/volatile parts is free — it adds a second lookup and an assembly step to every request, so confirm the shared part is actually expensive enough to be worth caching separately (see the related skill on caching things that are already cheap) before adding that complexity.

## Verify
After splitting the cache, remeasure hit rate specifically on the newly-isolated stable-part cache key (not the old combined key) and confirm it rises substantially, since that part's inputs should now repeat much more often across requests; separately confirm via a correctness test that responses still reflect the volatile input accurately (e.g., inventory count or personalization) within whatever precision was intentionally chosen.
