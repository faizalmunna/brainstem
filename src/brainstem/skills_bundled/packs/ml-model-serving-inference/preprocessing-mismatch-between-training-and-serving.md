---
name: preprocessing-mismatch-between-training-and-serving
description: A model performs well in offline evaluation but poorly in production because the feature preprocessing code used at serving time differs subtly from what was used during training.
triggers: ["training serving skew", "model works in offline eval fails in production", "preprocessing mismatch model degraded", "train serve feature skew"]
permissions: ["READ"]
---

## Symptom

A model shows strong performance metrics during offline evaluation
(against a held-out test set using the training pipeline's preprocessing)
but performs noticeably worse once deployed to production serving,
despite receiving inputs that should be logically equivalent -- a
classic training/serving skew.

## Likely causes

- **Preprocessing logic is implemented separately for training (often in
  a data science notebook or batch pipeline) and for serving (often in a
  production service, potentially a different language/framework)**, and
  the two implementations have subtly diverged -- a different rounding
  behavior, a different handling of missing values, a different
  tokenization edge case.
- **Feature values available at training time include information not
  actually available at serving time** (a form of data leakage), so the
  model learned to rely on something that's approximated differently or
  missing entirely in the real-time serving path.
- **A preprocessing step was updated for training (a new normalization
  constant, a new categorical encoding) without the corresponding
  serving-side code being updated to match**, since the two live in
  different codebases with no shared source of truth.
- **Timing-dependent features** (a "days since last purchase" type
  feature) are computed correctly at training time using historical
  data but computed differently or with different freshness at serving
  time, producing systematically different values for the same logical
  feature.

## Diagnose

1. Take a specific set of real production inputs and run them through
   both the training pipeline's preprocessing and the serving pipeline's
   preprocessing, diffing the resulting feature vectors directly to find
   exact discrepancies.
2. Check whether preprocessing logic is shared (a common library used by
   both training and serving) or independently implemented in two
   places, which is the single strongest predictor of this class of bug.
3. Review recent changes to either the training or serving preprocessing
   code for a change that wasn't mirrored on the other side.
4. For timing-dependent features specifically, verify that the serving-
   time computation reflects the same "as of" semantics the training
   data actually had.

## Fix

Use a single, shared preprocessing implementation for both training and
serving (a shared feature library, or a feature store that computes
features consistently for both offline training data generation and
online serving) rather than maintaining two independent implementations
that can drift. Where a shared implementation genuinely isn't feasible
(different languages/runtimes), build automated tests that compare
preprocessing output between the two implementations on the same inputs
as part of CI, catching divergence before it reaches production rather
than after a performance regression is noticed. Audit training-time
features for any that use information not genuinely available at serving
time.

## Pitfalls

Don't assume offline evaluation metrics are representative of production
performance without validating that the offline pipeline's preprocessing
genuinely matches serving -- a training/serving skew can make offline
metrics look great while the deployed model is meaningfully worse,
misleading the team about whether the model itself is actually good.

## Verify

After unifying or synchronizing preprocessing, run the diff-based
comparison from the diagnose step again across a representative sample
of real inputs and confirm feature vectors now match exactly (or within
an understood, acceptable tolerance) between training and serving paths.
Monitor production model performance after the fix and confirm it moves
closer to the offline-evaluated performance.
