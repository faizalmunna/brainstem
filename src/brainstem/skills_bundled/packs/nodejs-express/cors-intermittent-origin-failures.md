---
name: cors-intermittent-origin-failures
description: Diagnose browser requests to an Express API that fail with a CORS error only for specific origins, methods, or credentialed requests.
triggers: ["CORS error only in production", "CORS works for GET but not POST", "access-control-allow-origin missing intermittently", "preflight request fails", "CORS works for one origin but not another"]
permissions: ["READ"]
---

## Symptom
Browser requests to the API fail with a CORS error (`No
'Access-Control-Allow-Origin' header is present`, or a preflight `OPTIONS`
request failing) but not universally -- it works for some origins/domains
and not others, works for `GET` but fails for `POST`/`PUT`/`DELETE`,
works for simple requests but fails once credentials or custom headers
are involved, or works in one environment (staging) but not another
(production) despite the CORS middleware being "configured." Server-side
tools like `curl` or Postman often show the request succeeding, which
throws people off since the failure is actually enforced client-side by
the browser based on response headers.

## Likely causes
1. **A static, single allowed origin (or a hardcoded array) that doesn't
   include every real origin the API is actually accessed from** -- a
   `www.` vs. bare-domain mismatch, a staging subdomain never added, a
   mobile app's custom origin, or a new frontend deploy on a different
   domain -- so requests from the missing origin get no
   `Access-Control-Allow-Origin` header at all while others succeed.
2. **The CORS middleware doesn't handle the preflight `OPTIONS` request
   at all**, or handles it after another middleware/route already
   responded to `OPTIONS` with something else (a catch-all route, an
   auth middleware that rejects `OPTIONS` because it doesn't carry
   credentials) -- so any request that triggers a preflight (custom
   headers, non-simple methods like `PUT`/`DELETE`, `Content-Type:
   application/json` in some configurations) fails even though a plain
   `GET` from the same origin works fine.
3. **`credentials: true` is set on the client but the server responds
   with `Access-Control-Allow-Origin: *`** -- the CORS spec disallows
   the wildcard origin when credentials are involved, so browsers reject
   the response even though the server "allowed" the origin nominally;
   the fix requires echoing the specific requesting origin, not `*`.
4. **The allowed-methods or allowed-headers list is incomplete** -- a
   custom header the frontend sends (`X-Requested-With`, an
   `Authorization` header, a custom API-version header) isn't included
   in `Access-Control-Allow-Headers`, so only requests that happen not to
   need that header succeed.
5. **CORS headers are set inconsistently between success and error
   responses** -- middleware ordering puts the CORS middleware after a
   route that can throw/return early, so an error response path never
   gets the CORS headers attached and the browser reports a CORS failure
   even though the "real" problem is an unrelated 4xx/5xx.

## Diagnose
- Reproduce in the browser, not `curl`/Postman -- CORS is a browser-
  enforced policy based on response headers, so a request that
  "succeeds" via `curl` while failing in-browser is expected and not a
  contradiction; use the browser's Network tab and inspect the actual
  response headers on both the preflight `OPTIONS` (if one occurs) and
  the real request.
- For a failing case, check specifically: does an `OPTIONS` preflight
  happen at all (visible as a separate request in the Network tab before
  the real one)? If a preflight is expected (non-simple method or
  headers) but absent or erroring, that narrows to preflight handling;
  if the preflight succeeds but the real request's response is missing
  `Access-Control-Allow-Origin`, that narrows to per-route header
  application instead.
- Compare the `Origin` header the browser actually sends against the
  server's allowed-origin list/logic exactly, including scheme
  (`http` vs `https`), subdomain, and trailing differences -- CORS origin
  matching is exact-string, not a fuzzy domain match, so `https://app.
  example.com` and `https://www.app.example.com` are different origins
  even though a human would consider them "the same site."
- If credentials are involved, check the response header value for
  `Access-Control-Allow-Origin` specifically for a literal `*` -- that
  alone explains a credentialed-request failure regardless of anything
  else being configured correctly.
- Check where the CORS middleware is registered relative to other
  middleware and routes (see `middleware-order-breaks-auth-protection`
  for the general pattern) -- if it's registered after routes that can
  short-circuit the response (early error returns, a catch-all before
  it), some response paths never receive CORS headers.

## Fix
- Use a CORS middleware library (e.g. the `cors` package) configured
  with a dynamic origin-checking function (`origin: (origin, callback) =>
  {...}` checking against an explicit allowlist) rather than a single
  hardcoded string, so every real origin the API needs to serve is
  covered deliberately and the list is easy to audit in one place.
- Ensure the CORS middleware is registered before any route or other
  middleware that could respond to `OPTIONS` or return early, so
  preflight requests are always answered correctly and every response
  (including error responses) gets the CORS headers applied.
- When `credentials: true` is required, set
  `Access-Control-Allow-Origin` to the specific validated requesting
  origin (echoed back after allowlist validation), never `*`, and set
  `Access-Control-Allow-Credentials: true` explicitly.
- Explicitly list every custom header and method the frontend actually
  sends in `Access-Control-Allow-Headers`/`Access-Control-Allow-Methods`
  rather than relying on a library's defaults, and keep that list in
  sync when the frontend adds a new custom header.

## Pitfalls
- Setting `Access-Control-Allow-Origin` to `*` to "just make it work"
  silently breaks the moment credentials/cookies are introduced later,
  and also removes any actual origin restriction -- treat it as a
  deliberate security decision, not a quick fix, and prefer an explicit
  allowlist even when credentials aren't currently in use.
- Allowlisting an origin by a loose substring/regex check (e.g. matching
  anything containing `example.com`) can accidentally allow attacker-
  controlled subdomains or unrelated origins that happen to match the
  pattern -- match against an explicit, exact list of allowed origins.
- Fixing CORS for the main API routes but forgetting error-handling
  middleware or a catch-all 404 handler leaves CORS headers missing
  specifically on error responses, which shows up as "CORS is broken"
  reports that only reproduce when the underlying request is already
  failing for an unrelated reason -- apply CORS middleware globally,
  before routes, not per-route.

## Verify
From the browser (not curl), issue both a simple request (`GET`, no
custom headers) and a request that triggers a preflight (e.g. `PUT`
with a custom header or `Content-Type: application/json`) from each
origin the API is expected to serve, with credentials included where
applicable, and confirm both succeed with the expected data -- then
repeat from a deliberately non-allowlisted origin and confirm it's
correctly rejected, not silently allowed.
