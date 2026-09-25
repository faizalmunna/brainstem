---
name: negative-cache-result-missing-repeated-lookups-hammer-backend
description: Lookups for values that don't exist are never cached, so repeated requests for missing or not-yet-created records hit the backing store on every single request instead of just once.
triggers: ["404 lookups are hammering the database", "every request for a non-existent ID goes straight to the backend", "bots probing for random IDs are overloading the service", "cache only stores successful results not misses"]
permissions: ["READ"]
---

## Symptom
Requests for records that don't exist — a deleted item, a mistyped ID, a not-yet-provisioned resource, or a scanning/probing client trying many IDs — bypass the cache entirely and hit the backing store every time, even when the same non-existent key is requested repeatedly in a short window. The caching layer was designed only around the "found" path (cache the value on a successful lookup), so the "not found" path silently gets none of the cache's protection, and under any bursty pattern of repeated lookups for missing data (a broken client retry loop, a scraper, a race where a client polls for a resource before it's created) the backing store takes load proportional to request volume rather than to distinct real keys.

## Likely causes
1. **Cache-population code only runs on the success branch** — `if found: cache.set(key, value)` — with no equivalent for the not-found branch, because "cache the result" was written with only the happy path in mind.
2. **A negative/sentinel value was considered but rejected due to ambiguity** — the team worried a cached "not found" marker could be confused with a cache miss (both look like "nothing here"), so they avoided caching negatives rather than solving the ambiguity with a distinct sentinel.
3. **A client-side bug or retry storm repeatedly requests the same not-yet-created resource** (e.g., polling for a record immediately after triggering its async creation, before it exists) and every poll round-trips to the backing store because there's nothing to hit in the cache.
4. **Enumeration/scanning traffic** (malicious or just a broad crawler) requests many distinct non-existent keys, and because none of them are ever cached, the backing store absorbs the full brunt of every single request rather than the cache absorbing repeats of any given probed key.
5. **Negative caching exists in one code path but not another** — e.g., a REST API caches not-found responses but an internal RPC/service-to-service path for the same lookup doesn't, so the protection is inconsistent depending on caller.

## Diagnose
1. Check the cache-population code for the specific lookup and confirm whether the not-found branch calls any cache-set — often the answer is visibly no just from reading the function.
2. Query backing-store logs for repeated lookups of the same non-existent key within a short window (same ID, multiple requests, each resulting in a not-found) — this is the direct signature of the missing negative-cache behavior, and the request volume for that single missing key indicates the wasted load.
3. Check whether the traffic pattern causing load is concentrated on a small number of distinct missing keys requested repeatedly (negative caching would help enormously) versus a huge number of distinct missing keys each requested once (negative caching would help much less; the real problem is closer to abuse/rate-limiting).
4. Look for a client-side polling loop in logs/traces that requests the same resource ID multiple times in quick succession with not-found responses, which often points to a race between resource creation and the client that expects it to exist immediately.

## Fix
Cache not-found results explicitly using a distinct sentinel value (not `null`/absence, which is indistinguishable from "not in cache yet") so a subsequent lookup for the same key can return "confirmed not found" from the cache without touching the backing store. Give negative cache entries their own, typically much shorter, TTL than positive entries, since a not-found result is more likely to become stale soon (the resource might get created moments later) than a found result is to change — the right TTL balances protecting the backend from repeated misses against not blocking legitimate "check again after creating it" flows for too long. For the specific race of polling right after triggering async creation, consider a short negative TTL tuned to just under the expected creation latency, or a separate mechanism (a callback/webhook, or an explicit "creation in progress" state) rather than relying on cache TTL tuning alone to solve a timing problem.

## Pitfalls
Don't cache negative results with the same long TTL as positive results by default — a resource legitimately created moments after being cached as "not found" would then appear not-found for the full TTL duration even though a fresh backing-store lookup would find it, turning a performance optimization into a new user-facing bug. Also don't treat negative caching as a substitute for rate-limiting or bot mitigation against enumeration/scanning traffic that probes many distinct nonexistent keys — negative caching helps with repeated lookups of the *same* missing key, not with high-cardinality probing, which needs its own defense (rate limits, key-space validation before even attempting a lookup).

## Verify
Reproduce the repeated-lookup pattern for a known non-existent key (e.g., script N requests for the same deleted/never-created ID) and confirm via backing-store query logs or metrics that only the first request reaches the backing store while subsequent requests within the negative TTL are served from cache; separately confirm that creating the resource and querying again after the negative TTL expires correctly returns the now-found value.
