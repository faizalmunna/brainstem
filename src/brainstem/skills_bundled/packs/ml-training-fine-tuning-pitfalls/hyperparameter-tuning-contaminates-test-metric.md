---
name: hyperparameter-tuning-contaminates-test-metric
description: Hyperparameter tuning repeatedly evaluates against the same held-out split later reported as the final test metric, leaking tuning-process information into what should be an unbiased estimate.
triggers: ["test accuracy too good to be true after tuning", "final metric looks inflated after hyperparameter search", "used test set for hyperparameter tuning", "held out set leaked during tuning"]
permissions: ["READ"]
---

## Symptom

The training data itself was properly separated from evaluation data, but
the reported "test" metric is suspiciously high, doesn't reproduce on
genuinely new data after deployment, or drops noticeably when re-evaluated
on a freshly collected sample. Investigation reveals that the same split
called "test" was used, dozens or hundreds of times, to pick the best
learning rate, architecture variant, or regularization setting during
hyperparameter search -- so the reported number reflects the best of many
tries against that specific split, not a genuine held-out estimate.

## Likely causes

- **Only two splits exist (train/test) instead of three**, so when
  hyperparameter tuning needs a split to select against, the test set is
  the only one available and gets reused for both selection and final
  reporting.
- **A validation split exists but the final reported number is taken from
  whichever split (val or test) produced the best score**, effectively
  letting the tuning process cherry-pick which split's number to publish.
- **Automated hyperparameter search tools (grid search, Bayesian
  optimization, AutoML) are pointed at the test split by a config mistake**,
  especially in notebook-driven workflows where the split variable names
  are ambiguous or get reused across cells.
- **The same test set is reused across many independent experiments over
  time** (different team members, different weeks) without anyone tracking
  cumulative "queries" against it, so even careful individual experiments
  add up to overfitting the split at the project level.
- **Cross-validation folds are used for both model selection and reported
  performance** without a final untouched holdout, so the reported
  cross-validated score already reflects the fact that hyperparameters were
  chosen to maximize it.

## Diagnose

1. Trace exactly which data split every hyperparameter search trial
   evaluated against -- check the actual search/tuning code or experiment
   tracker logs (e.g., an Optuna study, W&B sweep) for the eval split
   argument, not just what the team believes it used.
2. Count how many distinct hyperparameter configurations were scored
   against the split now being reported as "test" -- more than a handful of
   evaluations against the same split for selection purposes is a leakage
   signal regardless of whether training data was clean.
3. Check whether a third, genuinely untouched split exists that was never
   referenced anywhere in the tuning code or experiment logs.
4. If no clean holdout exists, re-collect or carve out a new split from
   data that postdates the entire tuning process (e.g., a later time
   window) and compare the model's performance there against the reported
   test number -- a large gap confirms contamination.

## Fix

Enforce a strict three-way split discipline: train (for gradient updates),
validation (for hyperparameter selection, model/checkpoint selection, and
early stopping), and test (touched exactly once, after all tuning decisions
are frozen, purely to report a final unbiased estimate). Automate this as a
structural constraint rather than a convention -- e.g., the test split's
file/table is not even loaded into the tuning pipeline's code path, so it's
physically impossible for a search loop to reference it. For teams doing
extensive hyperparameter search, consider nested cross-validation (an outer
loop for unbiased evaluation, an inner loop for hyperparameter selection)
when data is too limited for a comfortable three-way split, and track every
evaluation against any split in an experiment tracker so cumulative usage
is auditable later.

## Pitfalls

Don't "fix" this by simply renaming validation to test after the fact --
if hyperparameters were already selected using that split's feedback, no
amount of relabeling recovers an unbiased estimate; the only real fix is
evaluating against data that was never used in any selection decision.

## Verify

After separating splits properly, retrain using only validation-split
feedback for all tuning decisions, freeze the final configuration, and
evaluate exactly once against the untouched test split. Confirm this number
is documented as final (no further tuning against it), and that it's
reasonably consistent with performance on an independent, later-collected
sample if one becomes available -- a large, systematic gap between the
"final" test metric and real-world performance after this fix indicates
remaining contamination elsewhere in the pipeline.
