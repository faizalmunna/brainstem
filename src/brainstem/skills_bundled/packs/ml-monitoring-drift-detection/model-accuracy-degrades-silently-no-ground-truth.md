---
name: model-accuracy-degrades-silently-no-ground-truth
description: A deployed model's real-world accuracy degrades over time with nobody noticing because ground truth labels for production predictions aren't available quickly enough to measure actual performance.
triggers: ["model accuracy dropped nobody noticed", "no ground truth for production predictions", "silent model performance degradation", "cannot measure production model accuracy"]
permissions: ["READ"]
---

## Symptom

A model's real-world prediction accuracy has clearly degraded (discovered
eventually through a business metric decline, a customer complaint, or a
manual spot-check), but nobody caught it through normal monitoring
because the actual correctness of the model's production predictions
can't be measured in near-real-time -- ground truth for what the model
predicted isn't available until much later, if at all.

## Likely causes

- **The prediction task's true outcome is only known after a significant
  delay** (predicting a 30-day customer churn outcome, for instance),
  so there's an inherent lag between a prediction being made and being
  able to verify it, during which degradation can occur entirely
  undetected by any accuracy-based monitoring.
- **No process exists to systematically collect ground truth for even a
  sample of production predictions**, relying instead on whatever
  eventually surfaces through unrelated business processes, which is
  neither timely nor comprehensive.
- **Monitoring exists for operational health (latency, error rate,
  request volume) but not for prediction quality specifically**, since
  operational monitoring is more straightforward to build and was
  prioritized, leaving quality monitoring as a gap.
- **The model's input distribution shifted significantly from what it was
  trained on**, and while this is detectable without ground truth (via
  distribution monitoring), no such proxy monitoring was set up either,
  so there was no early-warning signal available at all.

## Diagnose

1. Determine what ground truth data does eventually become available for
   this model's predictions, and how much delay exists between
   prediction and ground truth availability.
2. Check whether any process currently collects and joins ground truth
   back to historical predictions for accuracy measurement, even
   after the fact, or whether this connection has simply never been made.
3. Reconstruct historical accuracy (if any ground truth data exists
   retroactively) to identify roughly when degradation actually began,
   to help narrow down what changed around that time.
4. Check whether input distribution monitoring exists as a
   ground-truth-independent proxy signal, and if not, why it wasn't
   considered sufficient on its own.

## Fix

Build a pipeline that systematically collects ground truth (even if
delayed) and joins it back to the corresponding historical predictions,
producing an accuracy metric with whatever lag is inherent to the
task -- delayed accuracy monitoring is still far better than none. For
tasks with especially long ground-truth delay, add distribution-based
proxy monitoring (comparing production input feature distributions
against the training distribution) as an earlier warning signal that
doesn't require waiting for ground truth at all. Establish a target
maximum acceptable detection lag (informed by the ground-truth delay
that's actually achievable) and build alerting around accuracy dropping
below a threshold within that lag window.

## Pitfalls

Don't treat proxy monitoring (input distribution shift) as a full
substitute for actual accuracy monitoring once ground truth does become
available -- distribution shift doesn't always translate to accuracy
degradation and vice versa; use it as an early-warning complement, not a
replacement, once real ground-truth-based measurement is possible.

## Verify

Once ground-truth-joining is implemented, backfill historical accuracy
for a period covering the suspected degradation window and confirm it
actually shows the decline, validating the pipeline works correctly.
Confirm ongoing monitoring produces a fresh accuracy signal within the
expected lag window going forward, and confirm distribution-based proxy
alerts (if added) correctly fire on a deliberately introduced distribution
shift in a test scenario.
