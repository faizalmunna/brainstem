---
name: training-data-distribution-mismatches-production-traffic
description: A model with strong offline evaluation metrics underperforms in production because a specific real-world segment is over- or under-represented in the training data relative to live traffic.
triggers: ["good offline metrics bad real world performance", "model performs worse for certain user segment", "training data doesn't match production distribution", "covariate shift in deployed model"]
permissions: ["READ"]
---

## Symptom

Offline evaluation metrics look solid overall, but production monitoring
(or user complaints) reveals the model performs noticeably worse for a
specific, identifiable segment -- a device type, a geography, a new
user cohort, a language -- that barely appeared in the training set,
even though the model was never told to treat that segment specially and
nothing about the model architecture points to a bug.

## Likely causes

- **Training data was sourced from a period, channel, or user population
  that doesn't reflect current real-world traffic composition** -- for
  example, training data pulled predominantly from an older product
  version, a specific marketing channel's users, or a region where the
  product first launched, while production traffic has since diversified.
- **A recent product change shifted the real-world population** (a new
  platform launch, a new market, a pricing tier change) faster than the
  training data pipeline was refreshed, so the training set reflects a
  world that no longer exists.
- **Sampling during data collection was non-uniform without correction**
  -- e.g., logging infrastructure historically captured more events from
  power users, high-traffic regions, or a specific device type due to
  infrastructure placement, and that sampling bias was never
  reweighted before training.
- **A rare-but-important segment was deliberately or accidentally
  filtered out during data cleaning** (e.g., a "remove obvious bot
  traffic" filter that also strips out a legitimate but unusual usage
  pattern), shrinking that segment's representation far below its true
  production share.

## Diagnose

1. Compute the distribution of key segment variables (device type,
   region, user tenure, channel, language) in the training set and
   compare it directly against the same distribution measured from
   recent production traffic logs -- a side-by-side comparison, not just
   eyeballing summary statistics.
2. Break out the model's evaluation metric by segment on a production
   sample (not just the offline test set) and identify which segments
   show the largest metric gap relative to the overall average.
3. For any segment identified as underrepresented, trace the data
   pipeline's collection and filtering steps to determine whether the
   underrepresentation is a sourcing artifact, a filtering side effect,
   or a genuine underlying rarity.
4. Check the training data's collection date range against the current
   date and against any known product/market changes -- a stale
   collection window is often the simplest explanation.

## Fix

Reweight or resample the training data so its segment composition
matches current production traffic (inverse-propensity weighting, or
oversampling underrepresented segments) rather than assuming a uniformly
random historical sample is representative of today's traffic.
Where the mismatch stems from a stale collection window, refresh the
training data pipeline on a cadence tied to known product/market change
events, not just a fixed calendar schedule. Where a cleaning/filtering
step is inadvertently stripping a legitimate segment, narrow the filter's
criteria and re-validate that it isn't collateral-damaging real traffic
patterns it wasn't designed to touch.

## Pitfalls

Don't fix this by simply adding more overall training data without
correcting the segment composition -- collecting more data using the
same biased sourcing or filtering process reproduces the same skewed
distribution at larger scale and gives a false sense that the problem
was addressed through volume.

## Verify

Recompute the training-vs-production segment distribution comparison
after reweighting/resampling and confirm the gap has closed to within an
acceptable tolerance. Re-evaluate the retrained model's metric broken out
by segment against a fresh production sample and confirm the previously
underperforming segment's metric has moved measurably closer to the
overall average, then continue monitoring per-segment metrics
post-deployment rather than only the aggregate.
