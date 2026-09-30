---
name: regression-detected-but-no-suspect-commit
description: A latency or throughput regression shows up clearly in weekly dashboards but nobody can identify which of dozens of deploys caused it.
triggers: ["latency crept up but we don't know which deploy caused it", "performance regressed sometime this month", "can't find which commit caused the slowdown", "no per-deploy performance data to bisect with"]
permissions: ["READ"]
---

## Symptom

An aggregate metric (p95 latency, throughput, error-adjacent timeout
rate) is visibly worse than it was weeks ago, but tracing it to a cause
means investigating after the fact across dozens of intervening
deploys, feature flags, config changes, and traffic pattern shifts --
often ending in "we think it might be one of these three PRs" rather
than a confirmed root cause, because no performance signal was captured
at deploy time to bisect against.

## Likely causes

- **No per-deploy performance baseline is captured**, so there's no
  fine-grained timeline to compare against -- only a smoothed, weekly- or
  monthly-resolution dashboard that shows the drift only after it has
  accumulated across many changes.
- **Performance testing is treated as a reactive/incident-response
  activity** ("run a profile when something looks slow") rather than a
  standard, automated part of every deploy, so no data exists for the
  deploys that actually mattered.
- **Traffic mix changed over the same window** (more of a slow endpoint
  being called, a new large customer, seasonal load) independent of any
  code change, and without deploy-tagged metrics it's impossible to
  separate "code got slower" from "the same code is now doing more
  expensive work on average."
- **Metrics aren't tagged with build/deploy version**, so even if the
  regression window can be narrowed by eye, there's no way to correlate
  it precisely to a specific commit range without manually cross-
  referencing deploy logs and timestamps.

## Diagnose

1. Check whether metrics are tagged/annotated with deploy version or
   commit SHA (most APM tools support deploy markers/annotations on
   dashboards) -- if not, this is the actual root gap to close, and full
   attribution for the current regression may not be recoverable.
2. If deploy markers exist, overlay them on the latency/throughput graph
   and narrow the regression to the smallest bracketed window between
   two markers, then read the diff/changelog for exactly what shipped in
   that window.
3. Check for confounding traffic changes in the same window (request
   volume by endpoint, customer/tenant mix, payload size distribution)
   before concluding a code change is the sole cause.
4. If narrowed to a small set of candidate commits, use a canary or
   feature-flagged rollback of each candidate individually against a
   fixed load test or a subset of production traffic to isolate which
   one reproduces the regression.
5. As a last resort with no markers, use git bisect against a
   reproducible benchmark (if one exists) run against historical
   commits in a controlled environment matching production
   characteristics.

## Fix

Make performance visibility a first-class part of the deploy pipeline:
tag every deploy with a version marker on the relevant dashboards
automatically, and run an automated performance check (a fixed
benchmark, load test, or at minimum a before/after comparison of key
percentiles over a matched post-deploy window) as a standard CI/CD
step, not something invoked only after a regression is already visible
in aggregate. This turns "which of 40 deploys caused this" into "did
deploy #37 specifically regress the benchmark," answerable in minutes
instead of requiring retrospective archaeology.

## Pitfalls

Don't rely solely on synthetic per-deploy benchmarks as a complete
substitute for aggregate production monitoring -- a benchmark can miss
regressions that only manifest under real traffic shape or scale (see
the "microbenchmark improved but no end-to-end effect" pattern in this
pack, which is the mirror-image failure). The goal is deploy-level
granularity on top of production truth, not replacing one with the
other. Also avoid retroactively adding deploy markers only after an
incident and then treating the problem as solved -- the fix needs to be
standing infrastructure, not a one-time cleanup.

## Verify

Confirm that a dashboard for a key endpoint shows visible, queryable
deploy markers aligned to commit SHAs, and that triggering a deliberate
test regression (in a controlled environment) through the pipeline gets
flagged by the automated per-deploy check before or as soon as it
reaches the aggregate dashboard, rather than only becoming visible weeks
later.
