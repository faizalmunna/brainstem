---
name: aspnet-output-caching-stale-personalized-data
description: ASP.NET response caching or output caching serves one user's personalized page content to a different user because the cache key doesn't vary by identity.
triggers: ["wrong user sees cached data", "response cache leaking between users", "output caching personalized content", "cached page shows another user's info"]
permissions: ["READ"]
---

## Symptom

A user reports seeing data that belongs to a different user -- another
person's name, order history, or dashboard content -- on a page that
should be personalized to them, and the issue is intermittent and hard
to reproduce on demand, often correlating with recent traffic from
another user hitting the same URL.

## Likely causes

- **Response caching or output caching is enabled on an endpoint that
  returns personalized content**, with a cache key based only on the URL
  (and maybe query string), with no variation by user identity (cookie,
  auth header, or claims).
- **A shared cache layer (CDN, reverse proxy, ASP.NET's own output cache
  middleware) caches a response that included per-user data**, because
  the endpoint didn't set `Vary` headers or explicit cache-key
  customization to account for identity.
- **`[ResponseCache]` or output caching policy applied at a controller/
  action level too broadly** -- inherited from a base controller or
  applied via a filter that doesn't distinguish between genuinely public,
  cacheable actions and ones that render user-specific data.
- **Caching enabled during development/testing with anonymous requests
  only**, so the personalization-leak scenario never appeared until real
  concurrent multi-user traffic hit it in production.

## Diagnose

1. Identify the exact endpoint/URL involved in the report and check
   whether response caching or output caching is configured on it (
   `[ResponseCache]` attributes, `app.UseOutputCache()` policies, or a
   reverse proxy/CDN cache rule matching that path).
2. Reproduce with two authenticated sessions (two different real user
   accounts) hitting the same URL in quick succession and check response
   headers (`Cache-Control`, `Vary`, an `X-Cache`-style header from a CDN)
   to confirm whether the second request actually returned a cached
   response.
3. Check whether the cache key configuration includes anything
   identity-specific (a `VaryByHeader` for an auth header/cookie, a
   custom `IOutputCachePolicy` that varies by user ID) or only the URL.
4. Check for any intermediate shared cache (CDN, reverse proxy) between
   the client and the ASP.NET app that might be caching independently of
   the app's own caching configuration.

## Fix

For any endpoint returning personalized content, either disable response/
output caching entirely, or explicitly vary the cache key by user
identity (varying by an auth cookie/header, or a custom cache policy
keyed on the authenticated user ID) so different users never share a
cache entry. Reserve caching for genuinely public, identical-for-everyone
responses, and apply cache attributes/policies at the most specific level
(the individual action) rather than inherited broadly from a base
controller where it's easy to accidentally apply to a personalized
action added later. If a CDN or reverse proxy sits in front of the app,
confirm its caching rules independently -- disabling caching in the
ASP.NET app doesn't help if an upstream cache layer is caching based on
its own, separately configured rules.

## Pitfalls

Don't fix this by disabling caching everywhere as a blanket precaution --
that gives up a real performance benefit for genuinely public content;
scope the fix to the specific personalized endpoints instead. Also watch
for the inverse mistake when adding identity-based cache-key variation:
varying by a header/cookie that itself changes on every request (a
per-request anti-forgery token, a timestamp) effectively disables caching
without anyone realizing it, silently losing the intended performance
benefit.

## Verify

Reproduce the two-different-users-same-URL scenario again after the fix
and confirm each user's response reflects their own data, with response
headers showing either no caching for that endpoint or a cache key that's
correctly scoped per user. Load-test the still-cacheable public endpoints
separately to confirm they're still actually benefiting from caching
(cache hit rate as expected), so the fix didn't overcorrect into
disabling caching there too.
