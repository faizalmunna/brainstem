---
name: random-split-used-for-time-series-training-data
description: A time-series or sequentially dependent model looks accurate under cross-validation but degrades badly once deployed because the train/test split was randomized instead of time-based.
triggers: ["model works in backtest but fails live", "random split time series data", "cross validation score doesn't match production", "future data leaking into training set via split"]
permissions: ["READ"]
---

## Symptom

A forecasting, churn, fraud, or any other model trained on
sequentially/temporally dependent data shows strong, stable
cross-validation scores using a standard random k-fold or random
train/test split, but real-world (or properly time-ordered backtest)
performance is substantially worse, and the gap doesn't close no matter
how much the model architecture or hyperparameters are tuned.

## Likely causes

- **A standard random split (or random k-fold) was applied to
  time-ordered data**, so rows from "the future" relative to a given
  test row end up in the training set, letting the model implicitly
  learn from information that would never be available at real
  prediction time (macro trends, autocorrelated noise, a market regime
  shift already reflected training data).
- **The dataset contains multiple rows per entity across time (e.g.,
  multiple snapshots of the same user or account), and a random split
  puts different snapshots of the same entity into both train and test**,
  so the model partially memorizes entity-specific idiosyncrasies rather
  than learning generalizable temporal patterns.
- **A default library call was used without configuring it for
  time-series** -- e.g., `train_test_split(shuffle=True)` or default
  `KFold` instead of `TimeSeriesSplit`/a rolling-origin evaluation --
  because the team copied a generic ML template not built for temporal
  data.
- **Global feature engineering (scaling, imputation, encoding) was fit on
  the entire dataset before splitting**, which leaks future distributional
  information (like the global mean or max) into the training fold even
  if the split itself is later corrected.

## Diagnose

1. Inspect the exact split code: confirm whether shuffling is enabled and
   whether the split is a function of a timestamp column or purely
   random/stratified by label.
2. Check whether any single entity ID appears in both train and test
   sets -- group by entity ID and confirm no overlap when the underlying
   data represents repeated observations of the same entities over time.
3. Re-run evaluation using a strictly time-based split (train on data
   before date X, test only on data after date X) and compare that score
   against the original random-split score. A meaningful drop confirms
   the random split was inflating results.
4. Check whether scalers/encoders/imputers were `.fit()` on the full
   dataset versus `.fit()` only on the training partition before the
   split -- grep for `fit_transform` calls applied prior to any train/test
   partitioning.

## Fix

Replace random splitting with an explicit temporal split: train
exclusively on data up to a cutoff timestamp, validate/test only on data
after it, and if cross-validation is needed use rolling-origin ("walk-
forward") folds where every validation fold is strictly later in time
than its corresponding training fold. Refit all preprocessing
(scalers, encoders, imputers, target encoders) only on the training
partition of each fold and apply the fitted transform to
validation/test, never the reverse. For data with repeated
per-entity observations, additionally ensure entity-level grouping is
respected by the split (all of one entity's rows on the same side) so
temporal leakage and entity leakage are both closed.

## Pitfalls

Don't assume switching to a time-based split alone is sufficient while
leaving preprocessing fit on the full dataset -- a scaler fit globally
still leaks future distributional statistics (mean, variance, min/max)
into training even when row-level ordering is respected, producing a
subtler version of the same optimistic bias.

## Verify

Compare walk-forward cross-validation performance against a genuinely
held-out final time window the model has never seen during any tuning
step, and confirm the two are consistent with each other. If production
monitoring is available, confirm live performance over the first weeks
post-deployment tracks the walk-forward backtest numbers rather than the
original random-split numbers.
