---
name: global-target-encoding-leaks-label-information
description: A model with a target-encoded categorical feature performs implausibly well because the encoding was computed using each row's own label rather than out-of-fold statistics.
triggers: ["target encoding gives too good results", "mean encoding leaks label", "categorical encoding causes overfitting", "feature encodes the label itself"]
permissions: ["READ"]
---

## Symptom

A model that includes one or more target-encoded (mean-encoded)
categorical features shows a large, suspicious jump in performance
compared to the same model using one-hot or ordinal encoding of the same
features, and the target-encoded features consistently dominate feature
importance rankings -- but the improvement doesn't hold up on genuinely
new categories or in production, where the same encoding technique
produces far less informative values.

## Likely causes

- **Target encoding was computed globally across the entire training
  set** (each category replaced by the mean label value across all rows
  with that category, including the row being encoded itself), so for
  categories with few examples, a row's own label heavily influences its
  own feature value -- the model partially learns to read back the label
  through the encoding.
- **Target encoding statistics were computed before the train/validation
  split** rather than fit only on the training fold and then applied to
  validation, so validation rows' encoded features were influenced by
  validation labels that should have been held out entirely.
- **No smoothing or regularization was applied for low-cardinality
  categories**, so rare categories (a handful of rows) get an encoded
  value that's essentially a direct readout of those few rows' labels,
  an extreme case of the same leakage that's especially damaging because
  rare categories are disproportionately affected.
- **Encoding was fit once on the full dataset and reused across all
  cross-validation folds** instead of being refit independently inside
  each fold's training partition, so every fold's validation score is
  still contaminated even though the overall pipeline "looks" like it
  does cross-validation correctly.

## Diagnose

1. Check the target encoding implementation for whether it excludes each
   row's own label when computing that row's encoded value (out-of-fold
   or leave-one-out encoding) versus using a simple `groupby(category)
   ['label'].transform('mean')` computed on the whole dataset, which is
   the classic leaky pattern.
2. Compare model performance using the target-encoded feature versus a
   version with one-hot or ordinal encoding of the same categorical
   column -- an unusually large gap in favor of target encoding, well
   beyond what's typical for the technique, is the core tell.
3. Specifically inspect encoding behavior for low-frequency categories:
   check whether categories with very few training rows have encoded
   values equal or very close to their own rows' labels.
4. Verify whether the encoding is fit inside each cross-validation fold's
   training partition independently or computed once globally and reused
   across folds.

## Fix

Compute target encoding using out-of-fold statistics: for each row,
compute the encoding using only other rows (leave-one-out encoding), or
use a proper k-fold target encoding scheme where each fold's rows are
encoded using statistics computed from the other folds only. Apply
smoothing toward the global mean for low-cardinality categories
(shrinkage proportional to category count) so rare categories don't get
an encoding that's essentially their own label. Fit the encoding only on
each cross-validation fold's training partition and apply it to that
fold's validation partition, never computing it once on the full dataset
and reusing it everywhere.

## Pitfalls

Don't assume switching to a well-known library's target encoder
automatically avoids this -- some implementations default to global,
non-out-of-fold encoding unless explicitly configured otherwise, so the
leakage can persist even after adopting a "proper" library if the
relevant options (fold-based fitting, smoothing) aren't turned on.

## Verify

Recompute the target encoding using an out-of-fold or leave-one-out
scheme with smoothing, retrain, and confirm the performance gap between
target encoding and a non-leaky encoding (one-hot/ordinal) narrows to a
modest, plausible improvement rather than a dramatic jump. Specifically
re-check low-frequency categories to confirm their encoded values no
longer closely track their own rows' individual labels.
