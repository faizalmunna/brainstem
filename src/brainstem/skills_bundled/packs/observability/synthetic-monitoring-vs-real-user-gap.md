---
name: synthetic-monitoring-vs-real-user-gap
description: Synthetic/uptime checks report green while real users are actively experiencing errors or slowness -- the synthetic check isn't measuring what real usage actually does.
triggers: ["monitoring is green but users are complaining", "synthetic check passing but site is down for users", "uptime monitor says fine", "real user monitoring gap"]
permissions: ["READ"]
---

## Symptom

Synthetic monitors/uptime checks (Pingdom, a scripted health-check
endpoint, a simple `GET /health`) show 100% green throughout an incident
that real users are actively reporting -- support tickets, social media
complaints, or a spike in a real-user-monitoring/RUM tool tell a
completely different story than the synthetic dashboard.

## Likely causes

- **The synthetic check hits a trivial health endpoint** that doesn't
  exercise the actual code path users depend on (e.g., a `/health` route
  that just returns 200 without touching the database, cache, or
  downstream services that are actually failing).
- **The synthetic check runs from a location/network path that doesn't
  represent real users** -- from inside the same cloud region/VPC as the
  service, bypassing a CDN, load balancer, or geographic routing path that
  real user traffic goes through and where the actual problem lives.
- **The check doesn't cover an authenticated or personalized path** --
  most synthetic checks are unauthenticated for simplicity, so a failure
  specific to logged-in users, a specific user segment, or personalized
  content goes completely undetected.
- **The failure is intermittent/partial** (affecting a subset of
  requests, a specific region, a specific backend shard) and the
  synthetic check's low frequency or single vantage point has a real
  chance of simply not hitting the affected slice.
- **A client-side issue** (a bad frontend deploy, a broken JS bundle, a
  third-party script failure) that a server-side synthetic check
  structurally cannot see, since it never executes client-side code.

## Diagnose

1. Compare exactly what the synthetic check requests/asserts against what
   a real user's request actually exercises -- read the check's script
   line by line, don't assume it's representative.
2. Check the check's execution location(s) and frequency against real user
   geographic distribution and traffic volume -- a single-region,
   once-a-minute check has structurally low odds of catching a
   short-lived or geographically-scoped issue.
3. Cross-reference with real-user monitoring (RUM) data, error tracking
   (Sentry/similar), or support ticket volume for the same time window --
   if those show the problem clearly and the synthetic check doesn't,
   the gap is confirmed, not just suspected.
4. Determine whether the actual failure was server-side (should have been
   catchable with a better check) or client-side (structurally needs RUM/
   browser-based monitoring instead, not a better server check).

## Fix

Expand synthetic monitoring to exercise real critical user journeys
(login, checkout, core feature usage) end-to-end, not just a trivial
health endpoint, ideally reusing the same authenticated flows real users
go through. Run checks from multiple geographic vantage points matching
real user distribution, and increase frequency for the highest-value
journeys. Add real-user monitoring (RUM) as a complement, not a
replacement, specifically because it's the only way to see client-side-
only failures and genuinely reflects what users experience rather than
what a script from one location experiences. Treat synthetic monitoring's
job as "fast, cheap, always-on baseline coverage" and RUM/error tracking's
job as "ground truth for what users actually experienced" -- neither
alone is sufficient.

## Pitfalls

Don't make every synthetic check fully authenticated and journey-complete
if that meaningfully increases check latency/cost/flakiness for
high-frequency baseline monitoring -- keep a fast, simple, high-frequency
check for basic availability *and* add slower, deeper journey checks
separately; conflating the two makes the fast check less reliable as a
first-line signal. Also don't treat RUM data as automatically more
"correct" than synthetic data without accounting for its own biases (RUM
under-samples users with blocked analytics/ad-blockers, and can't easily
tell you about issues affecting users so badly they leave before any RUM
beacon fires).

## Verify

After expanding coverage, replay the exact conditions of the missed
incident (the same journey, the same affected region/segment if known)
against the new synthetic checks and confirm they would have caught it.
Track the gap between "time to synthetic-detected" and "time to first
user complaint" over subsequent incidents -- a successful fix narrows
that gap over time rather than leaving synthetic monitoring perpetually
behind real-user reports.
