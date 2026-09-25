---
name: single-seed-result-not-representative
description: A model trained with one random seed looks like a strong result, but performance varies significantly across seeds and only that single seed was ever actually evaluated.
triggers: ["results don't reproduce with a different seed", "model performance varies a lot by random seed", "only tested one seed", "seed variance in training results"]
permissions: ["READ"]
---

## Symptom

A reported result (a benchmark score, an A/B win, a paper's headline
number) comes from exactly one training run with one fixed random seed.
When someone later reruns training with a different seed -- often by
accident, or during an attempted reproduction -- the metric moves by an
amount large enough to change the conclusion (e.g., whether a new method
actually beats a baseline), revealing that the original single number was
a lucky draw rather than a representative estimate of the method's true
performance.

## Likely causes

- **Compute or time constraints led the team to run training once** and
  treat that run's result as *the* result, without budgeting for repeated
  runs to characterize variance.
- **The comparison being made (new method vs. baseline) never controlled
  for seed variance on either side**, so an apparent win could easily be
  within the noise band of seed-to-seed variation rather than a real
  effect of the change being tested.
- **Small datasets or small models amplify seed sensitivity** -- with
  fewer examples or fewer parameters, initialization and data-shuffling
  randomness has outsized influence on where training converges, making
  single-seed results especially unreliable in exactly the settings where
  teams are most tempted to skip repeats (fast, cheap runs).
- **Non-determinism beyond the explicit seed** (GPU nondeterministic
  kernels, data-loader worker ordering, distributed training race
  conditions) means even "the same seed" doesn't guarantee the same run,
  so the team may not even realize how much of their result is stochastic.
- **Early stopping or checkpoint selection based on validation performance
  compounds seed variance**, since the specific epoch selected as "best"
  is itself a noisy function of the seed's particular trajectory.

## Diagnose

1. Check the experiment log or paper/report for how many independent seeds
   were run for the headline result -- if it's one, that's the finding
   itself, not something to investigate further.
2. Re-run training with at least 3-5 different random seeds (same data,
   same hyperparameters, same code) and compute the mean and standard
   deviation of the metric across runs.
3. Compare the spread (standard deviation, or min-max range) across seeds
   against the size of the effect being claimed (e.g., new method beats
   baseline by 0.5 points) -- if the effect is smaller than the seed-to-seed
   standard deviation, the original single-seed comparison cannot support
   the claim.
4. Check whether "same seed" actually produces identical results by
   rerunning the exact same seed twice -- if it doesn't, there's
   unaccounted nondeterminism (e.g., nondeterministic GPU ops, unseeded
   data loader workers) inflating apparent variance further.

## Fix

Report results as a distribution across multiple seeds (mean ± standard
deviation, or a range), not a single number, for any result that will
inform a real decision (shipping a model, claiming a method improvement).
When comparing two methods or configurations, run both across the same set
of seeds and use a statistical comparison (e.g., checking whether
confidence intervals overlap, or a paired test across matched seeds) rather
than comparing two single-run point estimates. Budget compute for this
upfront -- if full multi-seed runs are too expensive, at minimum run the
final chosen configuration across several seeds before shipping, even if
earlier exploratory search used single seeds to save cost. Fix all sources
of nondeterminism that can be controlled (seed all RNGs: framework,
NumPy, Python's `random`, data loader workers; pin nondeterministic-kernel
flags where determinism matters more than raw speed) so that seed is
actually the only source of run-to-run variance being measured.

## Pitfalls

Don't cherry-pick which seed's result to report after the fact once
multiple seeds have been run -- reporting only the best of several seeds
after seeing all their outcomes reintroduces the same single-lucky-draw
problem this fix is meant to solve, just one layer removed.

## Verify

Confirm the reported metric for any shipped or published result includes
variance across at least 3 independent seeds, and that the specific claim
being made (e.g., "method A beats method B") holds when accounting for
that variance (non-overlapping confidence intervals or a significant paired
comparison), not just when comparing single best-case runs from each side.
