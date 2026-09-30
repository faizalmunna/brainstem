---
name: hyperparameter-search-finds-unstable-optimum
description: An automated hyperparameter search reports a best configuration whose validation score doesn't reproduce on rerun, because the search overfit to noise in a small or noisy validation signal.
triggers: ["best hyperparameters from sweep don't reproduce", "hyperparameter search result unstable on rerun", "optuna best trial performs worse when rerun", "hyperparameter tuning overfit to validation set"]
permissions: ["READ"]
---

## Symptom

An automated hyperparameter search (grid search, random search, Bayesian
optimization, an Optuna/Ray Tune sweep) runs many trials and reports a
"best" configuration with a strong validation score. When that
configuration is retrained (even with the same seed, or across a few
seeds), the score is noticeably lower than what the search reported --
sometimes only marginally better than configurations the search ranked far
lower. The search didn't find a genuinely better configuration; it found
one that happened to score well on a noisy validation estimate during that
particular trial.

## Likely causes

- **The validation set used to score each trial is small**, so the
  validation metric itself has high variance, and with enough trials
  (dozens to hundreds), the search reliably finds a configuration whose
  score is inflated by favorable noise rather than genuine superiority --
  a multiple-comparisons problem applied to hyperparameter search.
- **Each trial is evaluated with a single training run (single seed)**,
  so the search can't distinguish "this configuration is robustly better"
  from "this particular run got lucky," and with many trials the latter
  becomes common.
- **The search space includes hyperparameters with negligible real effect
  on performance**, adding noise dimensions that the optimizer can exploit
  to find spurious local optima without any of the changes being
  meaningfully causal.
- **Early trial pruning (stopping unpromising trials early to save
  compute) is miscalibrated**, cutting off configurations that would have
  improved with more training while letting through ones that happened to
  look good early but don't hold up, biasing the search toward
  early-favorable-but-unstable configurations.
- **The search optimizes directly against the same validation set used for
  final reporting**, compounding this instability with the separate
  problem of validation-set contamination if that same split is later
  reported as a test result.

## Diagnose

1. Retrain the search's reported "best" configuration multiple times with
   different seeds and compare the resulting score distribution against
   the single score the search reported for it.
2. Compare the top-N trials from the search (not just the single best) --
   if their scores are clustered tightly together with no clear separation
   from the reported "best," that's a strong noise signal rather than a
   real optimum.
3. Check the validation set size relative to the number of trials run --
   a small validation set combined with a large trial count is the
   clearest structural indicator of this failure mode.
4. Re-run a handful of the top trials with a larger or different
   validation sample (or k-fold validation) and check whether the ranking
   changes meaningfully from the original search's ranking.

## Fix

Evaluate each hyperparameter trial with more than a single noisy
estimate: use k-fold cross-validation per trial, or average across a small
number of seeds per configuration, especially for the top candidates
identified by a first coarse search pass. Increase the validation sample
size used for scoring trials if it's currently small relative to the
number of trials being run. After the search completes, don't trust the
single reported best blindly -- take the top handful of configurations and
re-validate them more rigorously (larger validation sample, multiple
seeds) before making a final selection, treating the search as a
candidate-generation step rather than the final decision-maker. Prune the
search space to hyperparameters with plausible real effect, reducing the
dimensionality the optimizer can exploit for spurious wins.

## Pitfalls

Don't respond to search instability by simply running more trials with
the same small, noisy validation setup -- more trials against a noisy
signal makes the multiple-comparisons overfitting problem worse, not
better, since it increases the chance of finding an even more extreme
lucky outlier rather than a genuinely better configuration.

## Verify

After re-validating top candidates with a more rigorous evaluation
(k-fold or multi-seed), confirm the finally selected configuration's
performance is consistent (low variance) across repeated retraining, and
that its advantage over the previous baseline configuration holds up
under this more rigorous evaluation, not just in the original search's
single-estimate ranking.
