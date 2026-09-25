---
name: learning-rate-misdiagnosed-as-data-or-architecture-problem
description: Training diverges, oscillates, or plateaus prematurely because the learning rate is miscalibrated, but the team spends time redesigning the architecture or auditing the dataset instead.
triggers: ["loss exploding to nan during training", "loss oscillating wildly and not converging", "training plateaus early and stops improving", "changed architecture but loss still unstable"]
permissions: ["READ"]
---

## Symptom

Training loss either explodes to NaN/Inf or oscillates wildly without
converging (too-high learning rate), or loss decreases for a few steps and
then flattens at a mediocre value far above what similar models achieve on
similar data (too-low learning rate, or one that decayed too aggressively).
Instead of first checking the learning rate, the team responds by
suspecting bad data (re-cleaning or re-labeling a dataset that's actually
fine), rewriting the model architecture, or blaming the loss function --
because the actual failure mode (LR miscalibration) produces symptoms that
superficially look like "the model can't learn this data."

## Likely causes

- **Learning rate was copied from a different model size, batch size, or
  optimizer than the one actually in use**, without adjusting for the fact
  that LR is not a portable hyperparameter across those changes.
- **No learning rate warmup for a large model or transformer-style
  architecture**, causing early-training instability (large gradient
  updates before the optimizer's moment estimates have stabilized) that
  looks like general instability rather than a specific warmup gap.
- **An LR scheduler decays too aggressively or too early**, effectively
  freezing the effective learning rate long before the model has converged,
  producing a premature plateau that looks like the model has "hit its
  ceiling" on this data/architecture.
- **Gradient clipping is absent while the learning rate is on the high
  side**, so occasional large gradients (from an unusual batch or an
  outlier example) cause a divergence spike that gets attributed to "bad
  data" rather than an LR/clipping gap.
- **Mixed-precision training amplifies instability from a marginal
  learning rate** that would have been merely suboptimal in full precision,
  making the divergence appear tied to the precision change or the
  architecture rather than the LR itself.

## Diagnose

1. Run a learning-rate range test (gradually increasing LR over a short
   warm-up run and plotting loss versus LR) to find the LR at which loss
   stops decreasing and starts increasing -- this directly locates where
   the current LR sits relative to the stable range, independent of any
   data or architecture hypothesis.
2. Re-run the exact same data and architecture with only the learning rate
   changed (e.g., reduced by 10x for suspected divergence, increased by
   3-10x for suspected premature plateau) before touching anything else --
   if the symptom resolves, the root cause was confirmed to be LR, not data
   or architecture.
3. Check for NaN/Inf specifically in gradient norms (not just loss) early
   in training -- a gradient norm spike immediately preceding a loss
   explosion is a strong LR/clipping signature, not a data-quality one.
4. Inspect whether a warmup schedule and gradient clipping are configured
   at all, since their absence is a common, easily-checked gap.
5. Plot the actual effective learning rate over training steps (post-
   scheduler) rather than assuming the configured peak LR is what's active
   at the point where the plateau begins.

## Fix

Treat learning rate as the first hyperparameter to isolate and rule out,
before architecture or data changes, precisely because its failure modes
(divergence, oscillation, premature plateau) are easy to misattribute.
Adopt a standard recipe: use a warmup period for large models, apply
gradient clipping as a safety net independent of getting the LR exactly
right, and use an LR range test or a small automated sweep (not a single
guessed value) before committing to a full training run. When reusing a
recipe from a different setup, always re-derive the learning rate for the
new batch size using an established scaling rule (e.g., linear or square-
root scaling with batch size) rather than copying the raw number.

## Pitfalls

Don't tune the learning rate by watching only the first few hundred steps
of training and declaring victory -- an LR that looks stable initially can
still be too high for the later, sharper regions of the loss landscape
once the model has partially converged, causing a divergence that appears
much later and gets misattributed to something that changed at that later
stage (e.g., a data shard boundary) rather than the LR set at the start.

## Verify

After adjusting the learning rate (and adding warmup/clipping if missing),
confirm the full training run completes without NaN/divergence and that
the loss curve reaches a materially lower value than the previous plateau,
using the identical data and architecture as the prior failed run. Confirm
this holds across at least one repeat run with a different random seed, to
rule out having simply gotten lucky with the new LR on one run.
