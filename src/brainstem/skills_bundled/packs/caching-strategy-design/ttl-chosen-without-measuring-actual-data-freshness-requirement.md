---
name: ttl-chosen-without-measuring-actual-data-freshness-requirement
description: A cache entry's TTL was picked as a round-number guess like 60 seconds or 24 hours instead of from the data's actual update frequency and business tolerance for staleness.
triggers: ["what TTL should I use for this cache", "cache keeps missing too often", "users are seeing old data even though we have a cache", "how long should we cache this API response"]
permissions: ["READ"]
---

## Symptom
A cache is in place and "working" in the sense that it returns hits, but one of two complaints keeps surfacing: either the backing store is still taking heavy load because the TTL is so short the cache barely helps (misses every few seconds on hot keys), or support tickets report users seeing data that's minutes-to-hours out of date after they changed it. Nobody can explain why the TTL is set to the value it is beyond "that's what the last person set it to" or "it's what the framework defaults to."

## Likely causes
1. **Copy-pasted default.** The TTL came from a framework example, a Stack Overflow answer, or another cache in the codebase for unrelated data, and was never revisited for this specific field's change rate.
2. **Never measured how often the underlying value actually changes.** A "user profile" cache and a "stock price" cache get the same TTL because they're both "just caching," when one changes weekly and the other changes every second.
3. **No stated staleness budget from the business/product side.** Engineering picked a number because nobody asked product "how stale can this be before it's a problem," so the number is a guess dressed up as a decision.
4. **TTL conflated with cache-memory-pressure tuning.** The TTL was shortened to fight eviction/memory issues rather than because freshness required it, coupling two unrelated concerns.
5. **One TTL applied uniformly across heterogeneous keys** in the same cache namespace (e.g., all "product" objects get 300s regardless of whether it's a flash-sale price or a rarely-changed description).

## Diagnose
1. Pull the actual update frequency of the underlying data: query the source of truth for `UPDATE`/write timestamps grouped by the entity type over the last 7-30 days (e.g., `SELECT date_trunc('hour', updated_at), count(*) FROM table GROUP BY 1`). Compare that histogram to the configured TTL.
2. Check cache hit-rate metrics segmented by key pattern (not aggregate) — a low hit rate on a specific prefix is a strong signal the TTL is shorter than warranted for that data's change rate.
3. Search support/incident history for "stale data" or "showing old" complaints tagged to this feature, and cross-reference the timestamps against the TTL window to confirm staleness is the actual cause rather than a missed invalidation (see the separate skill on invalidation gaps).
4. Ask explicitly, in writing, for the staleness tolerance: "if this value is wrong for N seconds after a write, is that acceptable?" Get a number, not a vibe, from whoever owns the feature.
5. Grep the codebase for the literal TTL value (e.g., `300`, `3600`) to see how many unrelated caches share it — a value reused across many call sites that touch different data is a red flag that it was never data-specific.

## Fix
Set TTL as a function of two independently-gathered numbers: the data's real-world change frequency, and the product's stated staleness tolerance — TTL should be the smaller of "how often it actually changes" and "how stale it's allowed to look." Document that reasoning as a comment next to the TTL constant, not just the number, so the next engineer doesn't have to re-derive it. For heterogeneous data sharing one cache namespace, split TTLs per key type rather than using one namespace-wide default. Where the freshness requirement varies by context (e.g., a price shown at checkout needs to be fresher than one shown in a browse list), consider a shorter TTL or bypass specifically for the high-stakes read path rather than lowering the TTL globally.

## Pitfalls
Don't swing to the opposite extreme and set TTL to match write frequency exactly with no margin — a value that changes every 10 minutes doesn't need a 10-minute TTL if reads can tolerate an hour of staleness; over-tightening TTL just re-introduces the backing-store load the cache existed to prevent, for freshness nobody asked for. Also avoid treating TTL as the only staleness control — if the business truly needs immediate consistency after specific writes, that calls for active invalidation on write (a different mechanism), not an ever-shrinking TTL chasing zero staleness.

## Verify
After changing the TTL, re-run the same update-frequency-vs-hit-rate comparison a week later: hit rate on that key pattern should rise measurably (e.g., from 60% to 90%+) without a corresponding increase in stale-data complaints. If hit rate rises but staleness complaints also rise, the TTL is now too long relative to the actual tolerance and needs to come back down or be paired with write-triggered invalidation.
