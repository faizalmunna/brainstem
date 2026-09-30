---
name: label-leakage-from-future-computed-feature
description: A model achieves suspiciously high offline accuracy because a feature is computed from data only available after the label outcome already occurred.
triggers: ["model accuracy too good to be true", "suspiciously high validation accuracy", "feature leaks the label", "leakage from future data in training set"]
permissions: ["READ"]
---

## Symptom

A model reaches accuracy, AUC, or F1 far above what similar published
work or business intuition would suggest is achievable -- sometimes
near-perfect on validation -- and the excitement is usually followed by
a much worse surprise once the model runs against real, live data,
where performance collapses back to (or below) a reasonable baseline.

## Likely causes

- **A feature is computed using a timestamp or aggregation window that
  extends past the prediction point**, such as a "total refunds on this
  order" feature that is only fully known after the order is resolved,
  used to predict whether the order will be refunded.
- **A feature is derived directly or indirectly from the label itself**,
  for example a "customer support contacted" flag that is set as a
  downstream consequence of the very churn event the model is trying to
  predict, rather than a cause or precursor of it.
- **Joins pull in a snapshot of a mutable table taken after the outcome
  window**, so a "current account status" column reflects the account's
  state today (post-outcome) rather than its state as of the prediction
  time, silently encoding the answer.
- **An aggregate or rolling feature is computed over the entire dataset
  (including future rows relative to each row's own timestamp)** instead
  of only over past rows, a common mistake with naive `groupby` +
  aggregate pipelines that don't respect per-row cutoff times.

## Diagnose

1. For each feature, ask: "could this value be known, in production, at
   the exact moment a prediction would actually be made?" Enumerate the
   feature's computation window and compare it against the label's
   outcome window explicitly, one feature at a time -- don't skip
   features that "look" like normal counts or flags.
2. Check feature importance / SHAP values for the trained model. A
   single feature with dramatically outsized importance relative to the
   rest is the single strongest tell of leakage and should be
   investigated before anything else.
3. Drop the suspect feature and retrain. A large, sudden drop in
   accuracy back to a plausible baseline confirms the feature was doing
   the leaking rather than genuinely predictive work.
4. Trace the feature's SQL or pipeline code for its `as-of` join key --
   confirm it joins against a point-in-time snapshot keyed by the
   prediction timestamp, not against the latest/current value of a
   mutable table.

## Fix

Rebuild every time-sensitive feature using point-in-time correct joins:
each training row's features must be computed as of that row's specific
prediction timestamp, using only data that existed and was recorded
before that instant, and a feature store or explicit "asof" join
(pandas `merge_asof`, or a temporal join in the warehouse) enforces this
mechanically rather than relying on manual discipline. Treat every
feature added to the schema as requiring an explicit answer to "what is
this feature's availability timestamp relative to the label's outcome
timestamp," and reject the feature into the pipeline until that's
documented.

## Pitfalls

Don't just remove the one obviously-leaking feature and declare the
problem solved -- leakage is rarely isolated to a single feature, and
teams that fix one instance without re-auditing the rest of the feature
set often ship a second, subtler leak later (e.g., a feature summarizing
"number of related events" that still spans past the cutoff for a
different reason).

## Verify

Rebuild the entire feature set from point-in-time correct joins, retrain,
and confirm accuracy lands within the range that domain baselines or
prior production models actually achieve -- not simply that it dropped.
Additionally, backtest the retrained model against a genuinely
out-of-time holdout (data from a period entirely after the training
window) and confirm performance there is consistent with cross-validation
performance, rather than degrading sharply.
