---
name: inconsistent-cache-key-construction-cross-user-data-leak
description: Different code paths build the cache key for logically the same data differently, one including a parameter like user ID or locale that another omits, causing either excess misses or one user's cached response being served to another.
triggers: ["one user saw another user's data", "cached response leaked between accounts", "cache key doesn't include the tenant so results are mixed up", "same endpoint sometimes cached correctly sometimes not"]
permissions: ["READ"]
---

## Symptom
Two variants show up, and both trace to the same root cause. The mild variant: hit rate is lower than expected because logically-identical requests generate different cache keys and never share a hit. The severe variant: a security incident where User A briefly sees User B's data, a response meant to be personalized (account balance, a personal dashboard, search results scoped to a tenant) gets served from a cache entry that was actually populated for someone else, because the key that stored it didn't include the parameter that should have scoped it.

## Likely causes
1. **A new filter, locale, or scoping parameter was added to the endpoint after caching was already in place**, and the cache-key logic wasn't updated to include it, so requests that differ only in that parameter collide on the same key.
2. **Key construction is duplicated across multiple code paths** (a REST controller and a GraphQL resolver, or a web app and a mobile API, both serving the same underlying data) and one path includes a dimension — user ID, tenant ID, permission level, currency — that the other omits.
3. **Case, ordering, or serialization differences produce different strings for logically equal inputs**: query parameters in a different order, an object serialized with different key ordering, or case-sensitivity differences (`en-US` vs `en-us`) that a naive key-builder treats as distinct when they should be identical, or as identical when they should be distinct.
4. **Authorization/personalization is applied after the cache lookup instead of being part of the key**, meaning the cache stores one shared response and an access-control or personalization layer is trusted to filter it per-request — if that later layer has a bug or is bypassed, the cache becomes the leak vector directly.
5. **A shared cache key omits a dimension that seems irrelevant but isn't** — e.g., caching a "product price" response without including currency or region, which works fine until the product is launched in a second region.

## Diagnose
1. Grep the codebase for every call site that builds a cache key touching this data and extract just the key-construction expressions; diff them for which request parameters, headers, or session attributes each one incorporates.
2. For a reported cross-user leak, get both users' request details (headers, auth context, query params) for the timeframe and reconstruct what cache key each request would have generated under the current logic — confirm they collide.
3. Check whether personalization/authorization filtering happens before or after the cache read/write in the code's execution order — if personalization happens after, the cached object itself may contain data that should never be shared, regardless of what's in the key.
4. Write a quick script that calls the endpoint with two requests differing only in the suspected missing dimension (e.g., two different user tokens, two different locales) and compare responses and any exposed cache-hit indicators (headers, timing) to confirm whether they're sharing an entry.
5. Audit for case/ordering normalization: check whether the key-builder lowercases, sorts, or canonicalizes inputs, and test with inputs that differ only in case or parameter order.

## Fix
Centralize cache-key construction into a single shared function (or a small typed key-builder) that every read, write, and invalidation call site is required to use — never let each call site format its own key string. Design the key schema explicitly by enumerating every dimension the response actually varies by (user/tenant, locale, currency, permission tier, API version, feature-flag state) and encode all of them in the key, not just the obvious ones; when in doubt about whether a dimension affects the response, include it — an extra dimension costs hit rate, a missing one costs correctness or security. Cache only data that's safe to share across whatever the key does NOT scope by; if a response must be personalized per-user, either include the user in the key or don't cache the personalized shape at all (cache the pre-personalization data and personalize after the cache boundary).

## Pitfalls
Don't respond to a leak by hastily adding the missing dimension to only the code path where the incident was noticed — the duplicated key-construction logic is the actual defect, and other call sites with the same duplication will leak on a different dimension later. Also resist the urge to include every conceivable request attribute "just in case" without checking hit-rate impact; a key that includes something that varies per-request but doesn't actually affect the response (like a request-id or timestamp) silently defeats caching entirely, which looks like a performance regression rather than a correctness bug and is easy to miss in review.

## Verify
Write a test that issues two requests with every combination of the dimensions the key is supposed to scope by (e.g., two users x two locales) and assert both that requests differing in a scoping dimension never receive each other's cached response, and that requests identical in every scoping dimension do share a cache hit (checked via a hit-count metric or an injected marker in the cached payload) — the first half of that test is what would have caught the leak, and the second half is what stops key over-inclusion from silently costing hit rate.
