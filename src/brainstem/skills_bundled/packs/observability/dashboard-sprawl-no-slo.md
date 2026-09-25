---
name: dashboard-sprawl-no-slo
description: Dozens of dashboards exist but nobody can answer "is the service healthy right now" quickly, because there's no defined SLO/SLI to check against.
triggers: ["too many dashboards", "no slo", "can't tell if service is healthy", "dashboard sprawl", "what does good look like"]
permissions: ["READ"]
---

## Symptom

During an incident or a routine health check, someone has to open several
different dashboards and eyeball a dozen graphs to guess whether the
service is okay, because there's no single, agreed "this number in this
range means healthy" indicator. Different engineers reach different
conclusions looking at the same graphs.

## Likely causes

- **Dashboards were built organically over time**, one per feature or
  incident, each showing whatever metrics seemed relevant at the time,
  with no pruning as the system evolved -- old dashboards for
  since-removed features still exist and get opened out of habit.
- **No SLI (service-level indicator) was ever explicitly defined** -- the
  team has metrics (latency, error rate, throughput) but never agreed
  which specific metric, at which percentile/threshold, actually
  represents "the user experience is fine."
- **Metrics are shown as raw values instead of against a target** -- a
  graph of p99 latency with no line marking the SLO target requires the
  viewer to already know what's acceptable, rather than showing it.
- **Different teams built dashboards with different implicit definitions
  of "healthy"** for the same service, so cross-team incident calls
  disagree about severity.

## Diagnose

1. During the next incident or health check, note how many dashboards get
   opened and how long it takes to reach a health verdict -- this is the
   direct cost of the sprawl, worth capturing concretely rather than
   arguing about in the abstract.
2. Ask each relevant team/on-call engineer independently what number they
   personally check first to decide "is this bad" -- if answers differ,
   there's no agreed SLI, just individual habits.
3. Audit existing dashboards for ones referencing removed features,
   decommissioned services, or metrics that no longer emit data --
   dead dashboards are pure noise in the search for the useful one.
4. Check whether any dashboard shows a target/threshold line at all, or
   only raw time series with no reference for "good."

## Fix

Define an explicit SLI/SLO per user-facing service (e.g., "99% of
requests complete under 300ms," "99.9% of requests succeed") through a
real conversation with stakeholders about what users actually tolerate --
not an arbitrary round number. Build one canonical "is this service
healthy" dashboard per service showing the SLI against its target
prominently (with an error-budget-burn view if the org tracks that), and
treat every other dashboard as a *drill-down* linked from that one, not a
competing top-level view. Archive or explicitly label dead dashboards
rather than leaving them discoverable alongside live ones. Make the
canonical dashboard the one thing paged on-call engineers are told to
open first.

## Pitfalls

Don't define an SLO so strict it's never actually achieved in practice
(chasing an aspirational number rather than a real one) -- an
unachievable SLO trains people to ignore the error budget entirely, which
is worse than not having one. Also resist adding "just one more metric"
to the canonical dashboard every time something new seems relevant --
that's exactly how the sprawl happened the first time; new signals belong
in a drill-down dashboard unless they change the actual health verdict.

## Verify

During the next real incident, time how long it takes to reach a
health verdict using only the canonical dashboard, and compare against
the earlier baseline measurement. Separately, confirm the SLO target is
periodically revisited (e.g., quarterly) against actual measured
performance and user complaints, so it stays a real, trusted number
rather than drifting into either "always green, meaningless" or
"never met, ignored."
