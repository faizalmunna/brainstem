---
name: target-leakage-through-data-augmentation-or-resampling
description: A model shows inflated validation performance because oversampling, augmentation, or synthetic data generation was applied before the train/validation split rather than after.
triggers: ["SMOTE inflated validation score", "augmented data leaked into validation set", "oversampling before split", "synthetic minority samples in test set"]
permissions: ["READ"]
---

## Symptom

Validation metrics are strong and improve further whenever oversampling,
SMOTE, or data augmentation is added to the pipeline, but the
improvement doesn't materialize in production or in a genuinely
independent holdout -- the model appears to get better specifically in
proportion to how aggressively resampling/augmentation is applied, which
is itself a red flag rather than a sign of real progress.

## Likely causes

- **Oversampling or SMOTE was applied to the entire dataset before
  splitting into train and validation**, so synthetic examples generated
  as interpolations of real minority-class points end up in the
  validation set, and those synthetic validation points are highly
  similar to real points that ended up in the training set -- the model
  effectively gets tested on near-duplicates of what it trained on.
- **Data augmentation (image rotation/crop/color-jitter, text
  paraphrasing, audio pitch-shifting) was applied before the split**, so
  augmented variants of a single original example are scattered across
  both train and validation, again producing near-duplicate leakage
  across the split boundary even though no single row is an exact
  duplicate.
- **Cross-validation folds were generated after a single global
  resampling pass** rather than resampling independently within each
  fold's training portion, so every fold's "held-out" data still contains
  synthetic points derived from that same fold's training data.
- **The pipeline's resampling step lives in a shared preprocessing
  function called once on the full dataset**, structurally making it easy
  to apply before splitting by default, since splitting happens in a
  separate, later step that the resampling code has no visibility into.

## Diagnose

1. Trace the exact pipeline order: locate the line where the train/test
   or train/validation split happens and the line where
   resampling/augmentation happens, and confirm which runs first.
2. If resampling ran before the split, check whether any generated
   synthetic or augmented example's nearest neighbor (by feature
   similarity or embedding distance) in the training set is suspiciously
   close to a validation-set example -- a high rate of near-neighbors
   across the split confirms leakage.
3. Re-run evaluation with resampling/augmentation moved strictly after
   the split (applied only to the training partition) and compare the
   resulting validation score against the original -- a meaningful drop
   confirms the original score was inflated by leakage.
4. For cross-validation specifically, verify whether resampling happens
   once globally or is re-executed independently inside each fold's
   training split via a pipeline object (e.g., `imblearn.pipeline.Pipeline`
   rather than manual global resampling followed by `KFold`).

## Fix

Move all resampling and augmentation strictly inside the training-fold
boundary: split first, then resample/augment only the training
partition, leaving the validation/test partition composed exclusively of
original, unmodified examples. For cross-validation, use a pipeline
abstraction that re-fits and re-applies resampling independently within
each fold rather than resampling once on the full dataset before folds
are created, so no fold's validation portion can ever contain synthetic
points derived from its own training portion.

## Pitfalls

Don't assume switching to a "proper" imbalanced-learning pipeline library
automatically fixes this -- many teams still call the resampler manually
outside the pipeline object for convenience or debugging, silently
reintroducing the same leakage that the library's pipeline abstraction
was specifically designed to prevent.

## Verify

Confirm via code inspection (or an automated check) that the split
precedes resampling/augmentation in execution order for every training
and cross-validation path in the pipeline, not just the main one.
Recompute validation metrics with the corrected ordering and confirm they
now sit at a level consistent with an independent, genuinely held-out
test set drawn from production-like data, rather than tracking upward
with more aggressive resampling.
