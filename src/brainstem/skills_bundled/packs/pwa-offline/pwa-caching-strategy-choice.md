---
name: pwa-caching-strategy-choice
description: Choose the right service worker caching strategy (cache-first, network-first, stale-while-revalidate) per resource type, instead of applying one strategy to everything.
triggers: ["which caching strategy service worker", "cache first vs network first", "stale while revalidate", "service worker strategy choice", "pwa caching design"]
permissions: ["READ"]
---

## Symptom
A PWA either shows stale data too often (because a resource that should
always be fresh is cached too aggressively) or feels slow/network-
dependent for content that could have been served instantly from cache --
usually because one caching strategy was applied uniformly to every
request type instead of being chosen per resource.

## Likely causes
This is a design-decision skill more than a single bug -- the recurring
mistake is treating "caching strategy" as one global setting rather than
a per-resource-type decision, since different resources have genuinely
different freshness requirements.

## Diagnose
Classify each type of resource the service worker handles:
1. **Immutable, versioned/hashed build assets** (JS/CSS bundles with a
   content hash in the filename) -- never change for a given filename, so
   staleness isn't possible by construction.
2. **The app shell / entry HTML** -- needs to reflect the latest deployed
   version so users pick up new versioned asset references.
3. **API data that changes frequently** (a live feed, real-time counts) --
   staleness is highly visible and undesirable.
4. **API data that changes rarely** (user profile settings, a product
   catalog) -- brief staleness is usually acceptable in exchange for speed
   and offline availability.
5. **Large, rarely-changing media** (images, fonts) -- similar to
   immutable assets if filenames are content-hashed; otherwise benefit
   from long-lived caching with an explicit invalidation path.

## Fix
- **Immutable hashed assets** -> cache-first with a long/indefinite
  expiry: since the filename changes whenever content changes, there's no
  staleness risk, only a speed benefit from skipping the network
  entirely once cached.
- **App shell / entry HTML** -> network-first (fall back to cache only
  when offline), so users get the latest shell whenever a network is
  available, and a reasonable offline experience otherwise (see
  `service-worker-stale-content` for the related update-detection
  mechanics).
- **Frequently-changing API data** -> network-first, or no caching at all
  if staleness is never acceptable for that specific endpoint -- treat
  offline behavior for this data as "explicitly show an offline/stale
  indicator" rather than silently serving old data as if it were current.
- **Rarely-changing API data** -> stale-while-revalidate: serve the
  cached response immediately for speed, while triggering a background
  fetch to update the cache for next time -- gives fast perceived
  performance without permanently freezing on old data.
- **Large media without content-hashed filenames** -> cache-first with an
  explicit, reasonable expiry/versioning scheme, since there's no
  filename-based invalidation to rely on.

## Pitfalls
- Applying stale-while-revalidate to data where staleness is genuinely
  unacceptable (a live inventory count that affects whether a purchase
  should be allowed) trades correctness for perceived speed inappropriately
  -- reserve it for data where brief staleness is truly a fine trade-off.
- Applying network-first to every request (as an overcorrection after
  being burned by a stale-cache bug) removes most of the offline/speed
  benefit a PWA is meant to provide -- the fix for a specific
  over-aggressive cache-first case is choosing the right strategy for
  *that* resource type, not abandoning caching broadly.
- Forgetting to set a cache-size or expiry limit on any long-lived cache
  can grow the service worker's cache storage unboundedly over time,
  particularly for cache-first media without content hashing.

## Verify
For each resource-type category, confirm behavior matches intent: hashed
assets load instantly from cache with zero network requests on repeat
visits; the app shell reflects the latest deploy when online; frequently-
changing data never shows an obviously-stale value without an offline
indicator; and stale-while-revalidate resources show cached content
instantly while updating in the background (confirm via a network tab
that the background fetch actually happens).
