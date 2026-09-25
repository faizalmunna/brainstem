---
name: multi-layer-cache-ttls-uncoordinated-inconsistent-staleness
description: A request passes through a CDN, an application cache, and a database query cache that each have independently configured TTLs, producing confusing and inconsistent staleness depending on which layer answered.
triggers: ["why does the same page show different data depending on which server answered", "CDN shows old content but the app cache already updated", "purging one cache didn't fix it, something else is still stale", "different staleness on different requests for the same URL"]
permissions: ["READ"]
---

## Symptom
The same logical request returns different freshness depending on seemingly random factors: sometimes the newest value, sometimes a value from minutes ago, sometimes from hours ago. Purging what the team assumes is "the cache" (usually the most visible one, like the CDN) doesn't reliably fix it, because there are two or three other caching layers between the client and the source of truth, each with its own TTL and invalidation rules that nobody documented together.

## Likely causes
1. **Each layer was added by a different team or at a different time**, each choosing a TTL that made sense in isolation (CDN team optimizes for edge cost, app team optimizes for backend load, DB team enables query cache by default) with no one owning the end-to-end staleness budget.
2. **Invalidation only reaches some layers.** A write triggers invalidation of the application cache but has no mechanism to purge the CDN edge cache or the database query cache, so those layers serve stale data until their own independent TTL expires.
3. **Layer ordering means a longer-TTL layer can mask a shorter-TTL layer's freshness.** If the CDN caches the app's response for 10 minutes but the app cache below it refreshes every 30 seconds, the CDN's TTL is the one that actually governs what users see — the shorter, "fresher" layer's tuning is irrelevant to end-user-observed staleness.
4. **Cache-control headers are set inconsistently or not propagated** — the origin sets a `Cache-Control` header intended for the CDN, but an intermediate proxy or the application framework overwrites or strips it, so the CDN falls back to a default TTL nobody chose intentionally.
5. **No single source of truth for "what is the maximum staleness a user can see."** Each layer's owner can truthfully say their layer is configured correctly, because "correctly" was never defined end-to-end.

## Diagnose
1. Map every caching layer in the actual request path, in order, with each one's configured TTL and invalidation trigger (or lack thereof) — draw it out: client → CDN → load balancer/reverse proxy → app cache → DB query cache → DB. Most incidents are diagnosed the moment this list actually gets written down, because it usually hasn't been.
2. For a specific stale-data report, check response headers (`Age`, `X-Cache`, `Cache-Control`, CDN-specific headers like `CF-Cache-Status` or `X-Cache-Hits`) on the actual affected request to identify which layer served the stale response, rather than guessing.
3. Compute the theoretical worst-case end-to-end staleness by summing the layers' TTLs that are on the response path (not layers bypassed by invalidation) and compare it against what users are actually reporting — if reported staleness exceeds even that sum, something else (like a broken invalidation, see the separate skill) is also at play.
4. Test invalidation reach directly: perform a write, then check each layer independently (raw app-cache lookup, direct-to-origin request bypassing CDN, a query against the DB cache status) to see which layers actually cleared and which didn't.

## Fix
Treat end-to-end staleness as one budget owned by one person or team, then allocate it across layers deliberately — e.g., "users can see data up to 2 minutes stale" might become CDN TTL 90s + app cache TTL 30s, with the sum staying under budget, rather than each layer independently picking a number that sums to something nobody approved. Make invalidation cascade in the same order the request flows: a write-triggered purge should hit every layer on the read path (CDN purge API call, app cache delete, DB query cache invalidation), not just the one layer the original author happened to be working in. Where a layer can't be actively invalidated (many CDNs are purge-eligible but slow, or purging is rate-limited), make that layer's TTL the shortest in the chain so it self-heals fastest, and document that decision.

## Pitfalls
Don't "fix" the confusion by disabling one layer entirely (e.g., turning off the CDN cache) as a quick patch — that trades a coordination problem for a capacity/latency problem and usually gets silently re-enabled later by someone unaware of the original issue, resetting the coordination gap. Also avoid setting every layer to the same TTL as a shortcut; layers serve different purposes (CDN protects against traffic spikes, app cache protects a specific expensive computation) and forcing uniform TTLs often makes the cheapest-to-invalidate layer (usually app cache) hold data as long as the hardest-to-invalidate one (usually CDN) for no reason.

## Verify
After reallocating TTLs and wiring cascading invalidation, perform a write and poll the actual public-facing endpoint (not any internal layer) at short intervals, recording the response headers each time; confirm the new value appears within the documented staleness budget on every attempt, not just most of them, and confirm via headers which layer served each response so the full chain is accounted for.
