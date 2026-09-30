---
name: shadow-deployment-never-actually-compared
description: A new model version runs in shadow mode alongside production but its predictions are never systematically compared against the live model, wasting the safety benefit shadow deployment was meant to provide.
triggers: ["shadow deployment not compared", "shadow model predictions never analyzed", "champion challenger no comparison done", "shadow mode running but not evaluated"]
permissions: ["READ"]
---

## Symptom

A new model version has been running in shadow mode (receiving live
production traffic and generating predictions, but not actually serving
them to users) for an extended period, intended as a safety check before
promoting it to production -- but nobody has actually systematically
compared its predictions against the current production model's
predictions, so the shadow deployment is providing no real validation
value despite the infrastructure cost of running it.

## Likely causes

- **Shadow predictions are logged, but no automated comparison pipeline
  was built to actually analyze them against the production model's
  predictions and against eventual ground truth**, so the raw data
  exists but nobody has a process turning it into an actionable
  comparison.
- **Setting up the shadow deployment infrastructure was treated as the
  main task**, with the comparison/analysis step planned as a follow-up
  that never got prioritized once the shadow deployment itself was
  "done" from an infrastructure perspective.
- **No clear promotion criteria were defined upfront** (what specific
  comparison result would justify promoting the shadow model to
  production), so even if someone looked at the data, there's no clear
  decision framework to act on it.
- **The team's attention moved to other priorities** once the shadow
  deployment was launched, treating it as a "set it and forget it"
  safety net rather than an active validation process requiring
  follow-through.

## Diagnose

1. Check whether shadow prediction logs actually exist and contain
   enough information (inputs, shadow model output, production model
   output) to perform a meaningful comparison.
2. Check whether any comparison analysis has been run at all since the
   shadow deployment started, and if so, how recently.
3. Review whether promotion criteria were ever explicitly defined, or
   whether the plan was always "we'll look at it and decide," which
   often means nobody circles back.
4. Assess the actual infrastructure cost of running the shadow deployment
   to quantify what's being spent for zero realized validation value
   currently.

## Fix

Build (or run, if only infrastructure was missing) an automated
comparison pipeline that regularly analyzes shadow model predictions
against production model predictions and, where available, against
ground truth -- producing a clear report of agreement rate, disagreement
patterns, and (once ground truth is available) relative accuracy.
Define explicit promotion criteria before or immediately after starting
a shadow deployment (a specific improvement threshold, a maximum
acceptable disagreement pattern) so the comparison data has a clear
decision attached to it. Assign explicit ownership and a review cadence
for shadow deployment results, treating it as an active process with a
defined endpoint (promote, reject, or extend with a specific reason) --
not an indefinite background state.

## Pitfalls

Don't leave a shadow deployment running indefinitely without a decision
being reached -- it accrues real infrastructure cost with no return once
the comparison isn't happening, and "we'll get to it eventually" tends to
mean never; set a concrete timeline for reaching a promote/reject
decision.

## Verify

Confirm the comparison pipeline actually produces a report analyzing a
representative sample of the accumulated shadow prediction data. Confirm
a concrete promote/reject/extend decision is made based on that report
against the pre-defined criteria, closing out the previously indefinite
shadow deployment state.
