---
name: batch-size-learning-rate-mismatch-causes-instability
description: Training becomes unstable or converges poorly after changing batch size because the learning rate wasn't rescaled to match, an interaction mistaken for an unrelated bug.
triggers: ["training got worse after increasing batch size", "changed batch size and now loss diverges", "larger batch size not converging as well", "gradient accumulation changed results unexpectedly"]
permissions: ["READ"]
---

## Symptom

After changing batch size -- often to use available hardware more
efficiently (larger batch on a bigger GPU) or to fit memory constraints
(smaller batch, or gradient accumulation to simulate a larger one) --
training becomes unstable (loss spikes or diverges) or converges to a
noticeably worse final result than before, with the learning rate left
unchanged from the previous batch size's working configuration. The team
often investigates data or code changes first since "we only changed the
batch size" doesn't intuitively look like the kind of change that should
break convergence.

## Likely causes

- **Batch size was increased without scaling the learning rate up to
  match**, leaving effective per-step learning too conservative for the
  now-larger, lower-variance gradient estimate, causing slow or stalled
  convergence.
- **Batch size was increased and learning rate scaled up naively (e.g.,
  linearly) without a warmup period**, causing early-training instability
  because large-batch, large-LR combinations are especially sensitive to
  the first few steps before optimizer statistics stabilize.
- **Batch size was decreased (often due to a memory constraint) without
  reducing the learning rate**, leaving effective learning too aggressive
  for the noisier, higher-variance gradient estimates from smaller
  batches, causing oscillation or divergence.
- **Gradient accumulation is used to simulate a larger batch size but the
  learning rate or loss normalization wasn't adjusted consistently**,
  producing an effective batch/LR combination that doesn't match either
  the small physical batch or the intended large simulated one.
- **Batch normalization statistics become unreliable at very small
  per-device batch sizes** (common with aggressive gradient accumulation
  or multi-GPU sharding), which looks like a training instability but is
  actually a batch-size-dependent normalization issue distinct from the
  learning rate itself.

## Diagnose

1. Confirm exactly what changed: batch size alone, or batch size plus any
   other setting (optimizer, precision, hardware) -- isolate the batch
   size change specifically before investigating anything else.
2. Compute the ratio of new batch size to old batch size and check whether
   learning rate was scaled by a comparable factor (linear scaling rule as
   a starting reference) -- an unchanged LR alongside a significantly
   changed batch size is the strongest signal for this root cause.
3. Re-run training at the new batch size with the learning rate scaled
   according to the standard rule (and with warmup added if increasing
   batch size substantially) as the single change, before investigating
   data or architecture.
4. For gradient accumulation setups, verify the loss is properly averaged
   (not summed) across accumulation steps and that the effective batch
   size used for any LR-scaling calculation matches the accumulated
   total, not the per-step physical batch.
5. Check batch normalization layer behavior specifically if per-device
   batch size is very small (e.g., under 8) -- consider whether
   normalization statistics are noisy enough to be a contributing factor
   independent of the learning rate.

## Fix

Treat batch size and learning rate as coupled hyperparameters, never
changed independently without reconsidering the other. Apply a scaling
rule when changing batch size (linear scaling for moderate changes, square-
root scaling in regimes where linear scaling causes instability) as a
starting point, then verify with a short training run rather than assuming
the formula is exactly right for the specific model and data. Add a
warmup period when scaling up both batch size and learning rate together,
since large-batch training is more sensitive to early instability. For
gradient accumulation, treat the accumulated effective batch size (not the
per-step physical batch) as the value driving any LR scaling decision, and
average rather than sum the loss across accumulation steps.

## Pitfalls

Don't apply the linear scaling rule blindly across a very wide batch size
range (e.g., 10x or more) without validation -- linear scaling breaks down
at very large batch sizes and can itself cause the instability it was
meant to prevent; treat it as a starting hypothesis to verify with an LR
range test at the new batch size, not a formula to trust unconditionally.

## Verify

After rescaling the learning rate to match the new batch size, confirm
training is stable (no divergence, comparable or better loss curve shape)
and that final validation performance matches or exceeds the previous
batch size's result within normal run-to-run variance. If throughput was
the original motivation for the batch size change, confirm the net effect
is actually a wall-clock training time improvement once the corrected
learning rate is accounted for.
