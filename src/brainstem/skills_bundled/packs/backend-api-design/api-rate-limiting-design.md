---
name: api-rate-limiting-design
description: Design API rate limiting that stops abuse without rejecting legitimate bursty traffic, and diagnose limits that are too strict or trivially bypassed.
triggers: ["rate limiting design", "429 too many requests", "rate limit too strict", "how to rate limit api", "rate limit bypassed", "throttle api requests"]
permissions: ["READ"]
---

## Symptom
Either legitimate users/integrations get `429 Too Many Requests` during
normal, bursty-but-reasonable usage (e.g. a bulk import, a dashboard
loading several widgets at once), or the rate limiting is trivially
bypassed (an attacker rotates IPs or accounts) while still blocking
well-behaved clients.

## Likely causes
1. **A fixed-window limiter** (e.g. "100 requests per minute, reset at
   the top of the minute") that allows a burst of 2x the intended rate
   right at the window boundary (100 requests in the last second of one
   window, then another 100 in the first second of the next), while also
   rejecting a smooth, well-behaved client that happens to send its 101st
   request just before a window resets.
2. **Rate limiting keyed only on IP address**, which over-throttles
   legitimate users behind shared NAT/corporate proxies (many real users,
   one IP) while under-protecting against an attacker who simply rotates
   IPs.
3. **No distinction between endpoint costs** -- a cheap read endpoint and
   an expensive write/search endpoint sharing the same limit, either
   over-restricting the cheap one or under-protecting the expensive one.
4. **Limits enforced only at the application layer**, so a flood of
   requests still consumes connection/thread capacity before ever
   reaching the rate-limit check, allowing a volumetric attack to degrade
   service despite the limiter "working."

## Diagnose
- Identify the current limiting algorithm (fixed window, sliding window,
  token bucket, leaky bucket) and whether it's per-IP, per-API-key, per-
  user, or some combination.
- For "legitimate bursts rejected," check whether the limiter is a strict
  fixed window with no burst allowance, or whether the intended usage
  pattern (a dashboard firing several requests at page load) was
  accounted for in the limit's sizing at all.
- For "trivially bypassed," check what the limiter actually keys on --
  if it's IP-only and the API requires authentication anyway, keying on
  the authenticated identity closes the easy-rotation bypass.

## Fix
- Prefer a **token bucket** or **sliding-window** algorithm over a naive
  fixed window: a token bucket allows a controlled burst (up to the
  bucket size) while enforcing a steady average rate over time, which
  matches how real clients actually behave better than a hard per-minute
  cliff.
- Key limits on the most specific reliable identity available:
  authenticated user/API key first, falling back to IP only for
  unauthenticated endpoints -- and consider a *combination* (per-key AND
  a looser per-IP ceiling) so a compromised/shared key doesn't let one
  bad actor exhaust the whole IP's budget for other legitimate keys.
- Set different limits per endpoint based on actual cost (expensive
  search/export endpoints get tighter limits than cheap reads), rather
  than one blanket limit for the whole API.
- Add a coarse limit at the infrastructure/edge layer (load balancer,
  CDN, WAF) in addition to application-level limiting, so volumetric
  floods are absorbed before consuming application resources.

## Pitfalls
- Returning a bare `429` with no `Retry-After` header forces well-behaved
  clients to guess when to retry, often making them retry too
  aggressively and prolonging the throttling -- always include
  `Retry-After` (or the rate-limit-remaining/reset headers convention).
- Rate limiting per-user-account for an API where creating a new account
  is free and easy doesn't actually stop abuse -- pair account-based
  limits with signal that's harder to launder (payment method on file,
  email verification age, behavioral signals) for abuse-prone endpoints.
- Setting limits based on a guess rather than actual traffic patterns
  either blocks real usage or lets real abuse through -- baseline actual
  legitimate usage patterns (P95/P99 request rates for real clients)
  before picking a threshold.

## Verify
Simulate the specific legitimate burst pattern that was previously
rejected (e.g. N requests fired near-simultaneously from one dashboard
load) and confirm it now succeeds, while a sustained-high-rate synthetic
client still gets throttled at the intended steady-state rate.
