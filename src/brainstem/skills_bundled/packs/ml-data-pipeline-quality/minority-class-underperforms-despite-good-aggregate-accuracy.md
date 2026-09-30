---
name: minority-class-underperforms-despite-good-aggregate-accuracy
description: A classifier reports strong overall accuracy but performs poorly on the minority class because severe class imbalance in the training data was never addressed.
triggers: ["high accuracy but bad recall on minority class", "model ignores rare class", "class imbalance hurting model performance", "fraud model misses most fraud cases"]
permissions: ["READ"]
---

## Symptom

A classifier reports an overall accuracy that looks good (often 90%+),
but when performance is broken out per class, the minority class (fraud,
churn, defect, rare disease, etc.) has dramatically worse
precision/recall than the majority class -- sometimes the model is
effectively predicting the majority class almost every time and coasting
on the fact that the majority class dominates the dataset.

## Likely causes

- **The training set's class distribution is heavily skewed (e.g., 98%
  negative / 2% positive) and no resampling, reweighting, or
  class-sensitive loss was used**, so a model that always predicts the
  majority class already achieves high accuracy, and gradient-based
  optimization has little incentive to fit the rare class well.
- **The evaluation metric itself is accuracy (or a similarly
  imbalance-insensitive metric)**, masking the real problem -- the model
  may actually be fine or actually be terrible on the minority class, but
  nobody can tell from the reported number.
- **Resampling (oversampling/undersampling/SMOTE) was applied before the
  train/test split rather than after**, meaning synthetic or duplicated
  minority examples generated from training data leak into the test set,
  making the imbalance problem look partially "fixed" while actually just
  adding evaluation leakage on top of it.
- **The imbalance is domain-realistic but the business cost asymmetry was
  never encoded** -- false negatives on the rare class (missed fraud,
  missed disease) are far more costly than false positives, but the
  model was trained and selected using a symmetric loss/metric that
  treats both error types as equally bad.

## Diagnose

1. Compute and report per-class precision, recall, F1, and a confusion
   matrix -- not just aggregate accuracy -- and check whether minority-
   class recall is near zero or far below majority-class recall.
2. Check the raw class distribution in the training set (`value_counts()`
   on the label column) and compare it against the real-world base rate
   the model will actually see in production; a mismatch in either
   direction changes the diagnosis.
3. Verify where in the pipeline any resampling step runs relative to the
   train/test split -- confirm resampling is applied only after splitting
   and only to the training partition.
4. Check whether the loss function or model has any class weighting
   configured (`class_weight='balanced'`, custom loss weights, or focal
   loss) versus using unweighted default loss.

## Fix

Address the imbalance explicitly rather than hoping the model figures it
out: use class weighting in the loss function proportional to inverse
class frequency, or apply resampling (oversampling the minority class,
undersampling the majority class, or SMOTE-style synthetic generation)
strictly within the training fold after splitting. Replace accuracy as
the primary model-selection metric with one sensitive to the minority
class (PR-AUC, F1 on the minority class, recall at a fixed precision
threshold) that reflects the actual cost asymmetry of the business
problem, and pick the decision threshold explicitly based on that cost
asymmetry rather than defaulting to 0.5.

## Pitfalls

Don't apply SMOTE or oversampling before splitting into train/test --
this is one of the most common imbalance "fixes" done wrong, and it
silently inflates test-set performance by leaking near-duplicate
synthetic minority examples across the split, producing a second, more
convincing but equally false sense that the imbalance problem is solved.

## Verify

Report per-class precision/recall/F1 and a full confusion matrix on a
held-out test set that was never touched by resampling, and confirm
minority-class recall/precision have measurably improved relative to the
pre-fix baseline at the chosen decision threshold. Additionally confirm
the chosen threshold was validated against the real business cost
tradeoff (e.g., cost of a missed fraud case vs. cost of a false alarm),
not left at the default.
