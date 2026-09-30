---
name: subtle-bug-in-feature-engineering-window-calculation
description: A model trains and predicts without error but learns a systematically wrong pattern because a rolling window or missing-value handling step has an off-by-one or boundary bug.
triggers: ["rolling average feature seems slightly off", "off by one in feature window", "model learns wrong pattern from feature bug", "missing values handled inconsistently in features"]
permissions: ["READ"]
---

## Symptom

The model trains without any errors, feature distributions look broadly
reasonable on a quick summary-statistics check, and the model even
achieves plausible accuracy -- but the model has learned something
subtly wrong: it systematically over- or under-weights certain patterns,
performs unexpectedly poorly on specific edge cases (the first few rows
of each group, entities with sparse history), or its learned behavior
doesn't match domain-expert intuition about what should matter, and
nothing about this is obvious from aggregate metrics alone.

## Likely causes

- **An off-by-one error in a rolling window definition** -- a "trailing
  7-day average" that actually includes the current day (leaking the
  current outcome partially into its own feature) or excludes one more
  day than intended, computed via an incorrectly configured window
  function or manual loop boundary.
- **Missing values are silently imputed with a value that isn't neutral
  for the feature's semantics** -- filling a "days since last purchase"
  gap with 0 (implying "just purchased," the opposite of the true
  meaning of "no purchase history") instead of a sentinel or the
  population's actual behavior for new entities.
- **A groupby-based feature computation doesn't reset correctly at group
  boundaries**, so a rolling calculation intended to be per-entity
  actually bleeds across entities when the underlying data isn't sorted
  correctly before the window operation, mixing one entity's history into
  another's feature.
- **A unit or scale mismatch introduced silently during feature
  engineering** -- a duration field switches between seconds and
  milliseconds partway through the pipeline's history, or a currency
  field mixes cents and dollars, producing a feature that's internally
  inconsistent even though every individual value is technically valid.

## Diagnose

1. For every rolling/windowed feature, manually compute the expected
   value for a small number of hand-picked example rows using a
   spreadsheet or independent script, and compare against what the
   pipeline actually produced -- this catches off-by-one and boundary
   errors that summary statistics won't reveal.
2. Check whether input data is sorted by the grouping key and timestamp
   immediately before any rolling/window operation runs; an unsorted or
   incorrectly-sorted dataframe is the most common cause of cross-entity
   bleed in groupby-based rolling calculations.
3. Plot the distribution of each imputed feature split by "was this value
   originally missing" vs. "was this value originally present" -- if the
   imputed value falls inside the range of real observed values rather
   than being clearly distinguishable, it's likely being treated by the
   model as a normal observation rather than a missingness signal.
4. Audit unit/scale consistency for every numeric feature across its full
   history, specifically checking for a version or date boundary where
   the source system or upstream pipeline changed how the value was
   recorded.

## Fix

Add unit tests for feature engineering functions that assert exact
expected output on small, hand-constructed input examples covering
boundary conditions (first row of a group, single missing value, window
exactly at the edge of available history) -- treat feature engineering
code with the same rigor as any other business logic, not as
throwaway data-munging. Use an explicit, distinguishable representation
for missingness (a separate "was_missing" boolean flag alongside a
sentinel value, or a model class that natively supports missing values)
rather than an imputation value that could plausibly be a real
observation. Always sort by grouping key and timestamp immediately before
any windowed operation, and add an assertion that verifies sort order
rather than assuming an upstream step already guaranteed it.

## Pitfalls

Don't assume that because the model "still trains and gets plausible
accuracy," feature engineering must be correct -- gradient-based models
are often robust enough to extract some signal even from features with
boundary bugs, which makes this class of bug the hardest to catch through
model performance alone and the most important to catch through direct
feature-level testing instead.

## Verify

Run the hand-computed boundary-case unit tests against the corrected
feature engineering code and confirm exact matches. Recompute the
affected features across the full historical dataset, diff the new
values against the old ones to quantify how many rows changed and by how
much, and retrain to confirm the model's behavior on the previously
problematic edge cases (sparse-history entities, group boundaries) now
matches domain expectations.
