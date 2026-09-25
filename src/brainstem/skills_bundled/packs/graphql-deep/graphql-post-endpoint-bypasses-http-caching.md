---
name: graphql-post-endpoint-bypasses-http-caching
description: A GraphQL API served over a single POST endpoint gets zero CDN or browser caching benefit even for queries that are safe to cache for minutes.
triggers: ["graphql not cached by CDN", "graphql cache-control header ignored", "why is graphql slower than rest for same data", "graphql cdn caching not working", "graphql browser cache POST"]
permissions: ["READ"]
---

## Symptom
A GraphQL API serving largely-static or slowly-changing data (product catalogs, content, config) shows no reduction in origin load or latency from a CDN sitting in front of it, and browser devtools show every GraphQL request hitting the network with no cache hit, even for queries that return identical results across many users -- while an equivalent REST endpoint for the same data would be trivially cached by URL.

## Likely causes
1. **All GraphQL requests are sent as `POST` to a single `/graphql` endpoint**, and HTTP caching (both browser and CDN/reverse-proxy layers) is fundamentally keyed on GET requests with cacheable URLs by default -- POST responses are not cached by standard HTTP semantics regardless of any `Cache-Control` header the server sends, because most caches specifically exclude POST from the cacheable method set.
2. **The server never sets `Cache-Control` headers on GraphQL responses at all**, treating every response as dynamic by default, even when a specific query result is safe to cache -- because a single endpoint serves both highly dynamic (current user's cart) and largely static (product description) queries, and no per-query caching policy was ever designed.
3. **Every request body (the query + variables) is unique or near-unique in ways that defeat any keying scheme even if GET were used** -- e.g. clients send full query documents with inconsistent whitespace/formatting, or embed non-deterministic ordering in field selection, so two logically-identical requests don't produce identical cache keys.
4. **The GraphQL client library defaults to POST for all operations without an option enabled for GET on cacheable (query, not mutation) operations**, so even after adopting persisted queries or automatic persisted queries, the client-side wiring to actually issue a cacheable GET was never turned on.

## Diagnose
- Inspect actual HTTP requests in the browser network tab or via `curl -v` against the GraphQL endpoint: confirm the method is POST and check whether any `Cache-Control`, `ETag`, or `Vary` response headers are present at all.
- Check the CDN/reverse-proxy configuration (CloudFront, Fastly, Cloudflare, nginx) for its default caching rules -- confirm whether it's configured to ever cache POST responses (most are not, by design) or whether a caching rule exists at all for the GraphQL path.
- Identify which specific queries in your operation set are actually cacheable (pure reads with no per-user variation, like a product catalog query) versus which are inherently per-user or mutating, since a blanket caching strategy for the single endpoint is the wrong target -- caching needs to be per-operation, not per-endpoint.
- Check whether persisted queries or automatic persisted queries (APQ) are already in use; if so, check whether the client is configured to send the persisted query hash as a GET request (`?extensions={"persistedQuery":...}`) rather than POST, since APQ over GET is the standard mechanism that makes GraphQL cacheable at all.

## Fix
Make specific, identified-safe GraphQL operations cacheable by giving them stable, cacheable HTTP semantics instead of trying to cache POST bodies:
- Adopt persisted queries (or automatic persisted queries) and configure the client to send cacheable read operations as `GET` requests with the query hash and variables in the URL query string -- this gives the operation a stable, deterministic URL that CDNs and browsers can cache using ordinary HTTP semantics, exactly like a REST endpoint.
- Set explicit `Cache-Control` (and `ETag` where response content allows revalidation) headers per-operation on the server, driven by an allowlist of known-cacheable operations (e.g. by persisted query ID), rather than a single blanket policy for the whole `/graphql` path -- mutations and per-user queries must remain `no-store` or `private`.
- Configure the CDN/reverse-proxy explicitly to cache GET requests to the GraphQL path when they carry a cacheable persisted-query hash, including `Vary` on any header that legitimately changes the response (e.g. `Authorization` for per-user data, if such queries are ever cached, which usually they should not be).
- For data that changes on a known cadence rather than per-request, consider a dedicated cached read path (a materialized response cache keyed by operation+variables server-side, e.g. via Redis) as a complement to HTTP caching, particularly for clients that can't be updated to use GET.

## Pitfalls
Naively switching all GraphQL traffic to GET to "unlock caching" without auditing which operations are safe to cache is dangerous -- a per-user or authenticated query cached by a shared CDN without proper `Vary`/private-cache handling can leak one user's data to another who happens to send a request that hashes to the same cache key, so operation-level cacheability review must come before any caching-layer change, not after.

## Verify
Send the same cacheable query twice via GET with a persisted query hash and confirm the second request returns an `X-Cache: HIT` (or provider-equivalent) header from the CDN with no origin request in server logs, then send a mutation or an authenticated per-user query and confirm it is never served from cache (correct `Cache-Control: no-store` or equivalent, and a cache MISS/BYPASS on every request).
