---
name: no-baseline-before-optimization-started
description: A team ships a performance optimization and cannot tell afterward whether it actually helped because no measurement was taken beforehand.
triggers: ["did that optimization actually help", "we forgot to measure before we started optimizing", "no before number to compare against", "can't tell if the change made things faster"]
permissions: ["READ"]
---

## Symptom

After shipping an optimization, someone asks "how much did this help?"
and the honest answer is "we don't know" -- the change felt necessary, it
was implemented and deployed, but no measurement of the specific target
metric was captured before the change went out, so there's nothing to
compare the current (post-change) number against beyond a vague memory
of things being "slow before."

## Likely causes

- **Optimization work started directly from a qualitative complaint**
  ("this feels slow") without first capturing a quantitative snapshot of
  the metric in question, so the "before" state only exists as an
  impression, not a number.
- **The wrong metric was captured as a baseline** -- e.g., a local
  benchmark timing was noted, but the change actually needed to be
  judged against a production percentile or a user-facing metric, and
  that number was never pulled before the deploy.
- **The baseline was captured but not scoped comparably** -- e.g., taken
  during a low-traffic period, or for a different endpoint/workload than
  the one ultimately changed, making any before/after comparison
  invalid even though a number technically exists.
- **Multiple changes shipped together** (the optimization bundled with
  unrelated feature work in the same deploy) so even a valid baseline
  and after-measurement can't be attributed to the optimization
  specifically versus the other changes.

## Diagnose

1. Before starting any optimization work, identify the exact metric,
   percentile, and measurement window that will be used to judge success
   (this is the same discipline as setting a numeric target, but applies
   even to changes made without a hard target -- the point here is
   having *a* comparable number, before and after, not necessarily a
   pass/fail threshold).
2. Pull and record the current value of that metric over a
   representative window (avoid unusually quiet or unusually loaded
   periods) before making the change, and note the traffic
   volume/conditions at the time so the after-comparison can use a
   matched window.
3. If a baseline was never captured and the question is being asked
   retroactively, check whether historical dashboards/metrics retain
   enough resolution and deploy-tagging to reconstruct an approximate
   before value (see the related skill on deploy-tagged metrics in this
   pack) -- otherwise, be explicit that the answer is genuinely
   unknowable and say so rather than guessing.
4. Check whether the optimization shipped bundled with other changes in
   the same deploy; if so, the after-measurement can't be cleanly
   attributed regardless of whether a baseline exists.

## Fix

Make "capture a baseline measurement, then make the change, then
measure again under comparable conditions" a mandatory first step of any
optimization task, not an afterthought -- treat it the same as writing a
test before fixing a bug. Ship performance-motivated changes in their
own deploy where feasible, separate from unrelated feature work, so the
before/after comparison is attributable to that change specifically.
Record the baseline somewhere durable (a ticket, a dashboard annotation,
a PR description) rather than only in memory, so the comparison can be
made by anyone later, not just the person who did the work.

## Pitfalls

Don't accept "it feels faster" or a single anecdotal test as a
substitute for a recorded quantitative baseline and after-measurement --
subjective impressions are unreliable for anything but the largest,
most obvious changes, and this is exactly the gap that leads to shipping
optimizations with unknown or negative real-world value (see the
microbenchmark and intuition-driven skills in this pack for what happens
downstream of skipping this step). Also don't capture a baseline under
unrepresentative conditions (e.g., a quiet Sunday) and compare it against
a post-change measurement taken during peak traffic -- normalize for
traffic/load conditions or the comparison is meaningless.

## Verify

Confirm that for the specific change in question, both a pre-change and
post-change value of the same metric, measured over comparable
conditions (traffic volume, time-of-day pattern, dataset state), are
recorded somewhere durable and attributable specifically to that change
-- and that the delta between them is large enough to be distinguishable
from normal metric variance/noise for that system, not just a difference
within the metric's usual day-to-day fluctuation.
