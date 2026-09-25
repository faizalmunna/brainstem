---
name: no-cache-hit-rate-monitoring-silent-ineffective-cache
description: A caching layer has no hit-rate or effectiveness monitoring, so it can silently degrade to near-zero hit rate and keep running as pure overhead without anyone noticing.
triggers: ["is our cache actually helping", "we have no idea what our cache hit rate is", "cache has been useless for a while and nobody noticed", "how do we know if caching is worth keeping"]
permissions: ["READ"]
---

## Symptom
A caching layer has existed for a long time, presumed to be helping, but there's no dashboard, metric, or alert that shows its hit rate or the load it's actually offloading from the backing store. When someone finally checks — often while investigating an unrelated performance issue — the hit rate turns out to be far lower than assumed (sometimes near zero), meaning the cache has been adding lookup latency, memory/infra cost, and a dependency-failure mode for a long time while providing little to no actual benefit, and nobody could have known because nothing was ever measured.

## Likely causes
1. **The cache was set up as an initial optimization with a one-time "it's working" check**, but no ongoing metric was wired up, so any later regression in effectiveness (from a code change, a data pattern shift, or a key-scheme change) has no way to surface.
2. **A silent key-mismatch or over-broad key change** (see the related skill on inconsistent key construction) gradually or suddenly dropped hit rate to near zero, and because nothing measured hit rate, the only visible symptom — if any — was a vague, hard-to-attribute increase in backing-store load that got investigated as a capacity issue instead of a caching regression.
3. **The cache technology's own dashboard shows infrastructure-level stats (memory used, connections, ops/sec) but not application-level hit/miss semantics** — the team mistakes "the Redis dashboard looks healthy" for "the cache is effective," which are different questions; a cache can be fully operational and still be useless if what it's storing is never re-requested.
4. **A traffic pattern shift changed cacheability** — e.g., a product change made requests more personalized/unique than before, or a client update stopped sending a previously-common query pattern — degrading a cache that was genuinely effective when built without any code change to blame.
5. **Ownership gap**: the team that built the cache moved on or the feature changed hands, and effectiveness monitoring was never someone's explicit responsibility, so a slow degradation has no natural point person to notice it.

## Diagnose
1. Check whether the cache client library or SDK exposes hit/miss counters natively (most do) and confirm whether those counters are actually being scraped into the metrics/observability system, not just available if someone queries the cache directly.
2. If no hit-rate metric exists at all, add one at the call site (increment a hit counter and a miss counter around every cache lookup) and let it run for a representative period (spanning normal traffic variation, e.g., a full week) before drawing conclusions.
3. Where a hit-rate metric already exists but nobody looked at it, pull the historical time series (most metrics backends retain history) and check whether effectiveness degraded gradually over time or dropped sharply at a specific point — a sharp drop usually correlates with a deploy and points to a specific code change as the cause.
4. Segment hit rate by key pattern/endpoint rather than looking only at an aggregate number — an aggregate can look "acceptable" while masking one specific high-traffic key pattern that's actually at zero.

## Fix
Instrument every cache lookup with a hit/miss counter (most cache client libraries support this with a thin wrapper if not built in) and put hit rate, broken down per key pattern or logical cache name, on a dashboard next to the backing-store load metric it's meant to protect — the two side by side make it obvious whether the cache is doing its job. Set an alert threshold for a meaningful hit-rate drop (not just an absolute low value, since some caches are legitimately low-hit-rate by design) so a regression triggers investigation automatically instead of waiting for someone to notice degraded backing-store performance and trace it back manually. Assign the cache an explicit owner or make its effectiveness part of an existing service's regular health review, so "is this cache still worth its complexity" gets asked periodically rather than never.

## Pitfalls
Don't treat a single point-in-time hit-rate check as sufficient and move on — effectiveness can and does drift after the check (new code paths, changed traffic patterns), which is exactly the silent-degradation failure this skill describes; the fix is ongoing monitoring, not a one-time audit. Also avoid alerting on a fixed hit-rate threshold copied from another cache without considering that a low but positive hit rate can be entirely appropriate for a low-cardinality-benefit cache while a high threshold makes sense for another — calibrate the alert to each cache's own historical baseline rather than a generic number.

## Verify
Confirm the hit-rate metric is visible on a dashboard and has been continuously populated (not gapped) for at least one full traffic cycle, then deliberately introduce a synthetic regression in a test environment (e.g., temporarily break key consistency or shorten TTL drastically) and confirm the alert fires within the expected time window — this proves the monitoring would actually catch a real future regression, not just that a metric exists.
