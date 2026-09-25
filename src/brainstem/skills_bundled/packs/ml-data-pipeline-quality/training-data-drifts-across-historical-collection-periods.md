---
name: training-data-drifts-across-historical-collection-periods
description: A model trained on a long historical window underperforms because the input feature distributions drifted significantly between the earliest and most recent training examples.
triggers: ["training data spans a period with distribution drift", "model trained on stale historical data underperforms", "feature distributions changed over training window", "concept drift within training set itself"]
permissions: ["READ"]
---

## Symptom

A model trained on a large historical window (a year or more of data,
often pulled because "more data is better") performs worse than a
similar model trained on a smaller, more recent window -- or performs
inconsistently depending on which time slice of the training data is
examined -- because the relationship between features and label, or the
feature distributions themselves, changed meaningfully somewhere within
the training period itself, and averaging over the whole window teaches
the model a blended pattern that matches no single period well.

## Likely causes

- **A real-world concept drift occurred within the training window** (a
  pricing change, a product redesign, a shift in user behavior, a
  macroeconomic change) such that the true function mapping features to
  label is genuinely different in the early portion of the training data
  versus the late portion, but the model is trained as if one stationary
  function applies throughout.
- **An instrumentation or logging change occurred mid-window** -- a
  tracking library upgrade, a new event schema, a change in how a
  feature is computed upstream -- so part of the training window has
  systematically different feature values for reasons unrelated to any
  real-world change, purely due to how the data was measured.
- **Old data reflects a different product surface or user population
  than the current one** (an old app version, a discontinued feature, a
  market since exited), and its inclusion in the training set dilutes
  the signal that's actually relevant to current production traffic.
- **No recency weighting or windowing was applied when assembling the
  training set** -- all historical data available was used with equal
  weight regardless of age, on the assumption that more historical data
  is strictly better, without checking whether the extra history is
  still representative of the present.

## Diagnose

1. Split the training window into several sequential time slices (e.g.,
   by quarter) and compare feature distributions and label rates across
   slices -- a statistical drift test (population stability index,
   Kolmogorov-Smirnov test) between the earliest and latest slice
   quantifies whether meaningful drift occurred.
2. Train separate models on individual time slices and compare their
   learned feature importances or coefficients across slices; a feature
   that matters a lot in one slice and not at all in another indicates
   the relationship itself has drifted, not just the raw feature values.
3. Evaluate a model trained only on the most recent N months against one
   trained on the full historical window, both against a recent held-out
   test set, to directly test whether the older data is helping or
   hurting.
4. Cross-reference any detected drift points against known product,
   instrumentation, or market events (a changelog, a deployment history)
   to distinguish real concept drift from a measurement artifact.

## Fix

Where drift is due to a genuine change in the world, either restrict
training data to the window after the change (accepting less data in
exchange for a consistent underlying relationship) or explicitly weight
more recent examples more heavily (exponential recency weighting) so the
model prioritizes the current regime while still benefiting from older
data's volume. Where drift is due to an instrumentation/logging change,
either exclude the affected pre-change period entirely or reprocess it
through a compatibility transform so it matches the current schema's
semantics before inclusion. Re-evaluate the appropriate training window
length periodically rather than treating "use all available history" as
a permanent default.

## Pitfalls

Don't assume more historical data is always better without checking --
teams often extend a training window purely to increase row count, which
can quietly dilute a model's fit to current conditions if a meaningful
fraction of that additional data reflects a world that no longer exists.

## Verify

After restricting or reweighting the training window, compare the
retrained model's performance against a recent, unseen test set to the
previous full-history model's performance on the same test set, and
confirm the corrected model performs at least as well. Re-run the
sequential time-slice drift comparison on the new training set and
confirm the earliest and latest slices are now statistically consistent
within the retained window.
