---
name: ttfb-missing-cache-headers-origin-refetch
description: Fix slow TTFB caused by missing or misconfigured cache-control headers forcing the CDN or browser to refetch content from origin every time.
triggers: ["CDN not caching pages", "cache-control headers missing", "every request hits origin server", "TTFB slow despite CDN", "cache-control max-age misconfigured"]
permissions: ["READ"]
---

## Symptom
The site sits behind a CDN, yet TTFB is consistently slow for content that
should be cacheable (static marketing pages, rarely-changing API
responses, images) -- distinct from the cold-database-connection skill
because the origin server itself may be perfectly fast; the problem is
that requests are reaching it at all when they shouldn't need to.

## Likely causes
1. **No `Cache-Control` header set at all**, so the CDN/browser falls back
   to conservative default heuristics (often no caching, or very short
   TTLs) instead of an intentional policy.
2. **`Cache-Control: private` or `no-store` applied broadly** (e.g. a
   framework default that marks all responses non-cacheable for safety,
   or a security-conscious blanket policy) even for genuinely public,
   shareable content.
3. **Cache key includes a per-user or per-request varying value**
   (session cookie, random query param, `Vary` header on something that
   differs per request like `Accept-Encoding` combined with inconsistent
   encoding) that causes the CDN to treat every request as a unique,
   uncached miss.
4. **CDN configuration overrides origin headers** with its own shorter
   default TTL, or a caching rule that excludes the specific path pattern
   being tested, so origin headers are correct but ignored.
5. **Frequent cache purges/invalidations** (e.g. a deploy pipeline that
   purges the entire CDN cache on every deploy) keep effectively resetting
   the cache to cold state even though the policy itself is fine.

## Diagnose
- Check the response headers in DevTools Network for `Cache-Control`,
  `Age`, and the CDN's own cache-status header (e.g. `X-Cache: HIT/MISS`,
  `CF-Cache-Status`, `X-Vercel-Cache`) -- a `MISS` or `Age: 0` on a repeat
  request to unchanged content confirms it isn't being served from cache.
- Request the same URL twice in a row and compare `Age` headers -- if
  `Age` doesn't increase between requests, nothing is actually being
  cached regardless of what `Cache-Control` claims.
- Check the `Vary` header and the actual request headers that differ
  between "cache miss" requests -- a `Vary: Cookie` combined with every
  request carrying a unique session cookie explains why nothing hits.
- Review CDN dashboard cache-hit-ratio metrics for the specific path
  pattern, and check deploy/purge logs for correlation between deploys and
  cache-hit-ratio drops.

## Fix
Make cacheability an explicit, intentional decision per response type
instead of relying on defaults, and make sure the cache key only varies on
dimensions that actually change the response. Concretely: set explicit
`Cache-Control: public, max-age=..., s-maxage=...` (with `s-maxage`
controlling CDN TTL separately from browser TTL) on genuinely public,
shareable responses; strip session cookies/auth headers from requests to
cacheable routes (or move personalization to a client-side fetch/edge
function that runs after the cached HTML shell is served) so the CDN
cache key isn't polluted by per-user values; use `stale-while-revalidate`
so the CDN can serve a slightly-stale cached response instantly while
refreshing in the background, rather than blocking the user on a fresh
origin fetch; and replace full-cache purges on deploy with targeted
invalidation of only the paths that actually changed, or use versioned
asset URLs so most content never needs purging at all.

## Pitfalls
- Setting a long `max-age` on content that does change (e.g. a
  user-specific dashboard accidentally marked public) serves stale or
  wrong data to the wrong users -- confirm the response is truly
  identical for all requesters before making it publicly cacheable.
- `stale-while-revalidate` masks a slow origin rather than fixing it -- if
  the background revalidation itself is slow, the *next* stale window's
  freshness degrades; still address root origin latency for content that
  changes often.
- Purging the CDN on every deploy "to be safe" reintroduces this exact
  problem after every release -- scope purges to changed paths.

## Verify
Request the affected URL twice from a location outside your own network
(or via WebPageTest from multiple regions) and confirm the CDN cache
header shows `HIT` with a growing `Age` on the second request, then
re-measure TTFB via PageSpeed Insights/CrUX field data to confirm it
dropped for repeat visitors and cache-served first-time visitors alike.
