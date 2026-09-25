---
name: multi-task-fine-tuning-imbalance-starves-secondary-task
description: Fine-tuning on a mixture of multiple tasks or datasets produces strong performance on the dominant task while a smaller or harder secondary task barely improves or gets worse.
triggers: ["multi-task fine-tuning one task not improving", "combined dataset training only helps the bigger task", "secondary task performance stagnant during joint training", "task mixture imbalance during fine-tuning"]
permissions: ["READ"]
---

## Symptom

A model is fine-tuned on a combined dataset spanning multiple tasks or
domains (e.g., general instruction-following plus a specialized task, or
multiple product categories in one classifier), with the intent of
improving all of them together. After training, the task or domain with
more examples shows clear improvement, while a smaller or intrinsically
harder secondary task shows little improvement, no improvement, or even
regresses relative to a model fine-tuned on that task alone -- the joint
training implicitly prioritized whichever task dominates the loss signal.

## Likely causes

- **The tasks are mixed in proportion to raw example counts rather than
  by any deliberate weighting**, so a task with 10x more examples
  contributes roughly 10x more gradient signal per epoch, regardless of
  its actual importance or difficulty.
- **Tasks have different natural loss scales or difficulty**, so even at
  equal example counts, the optimizer's gradient updates are dominated by
  whichever task's loss has larger magnitude or noisier signal, unless
  explicit loss weighting or normalization accounts for this.
- **No per-task validation tracking exists during training**, so the
  aggregate loss or metric looks fine (dominated by the larger task) while
  the secondary task's degradation goes unnoticed until a separate,
  dedicated evaluation is run after the fact.
- **Shared representation capacity is insufficient for both tasks**,
  especially with parameter-efficient fine-tuning at a low adapter rank,
  so the optimizer effectively has to choose which task's patterns to
  encode given limited additional capacity, and the loss-dominant task
  wins that implicit competition.
- **Batching strategy interleaves tasks unevenly** (e.g., epochs cycle
  through the larger dataset multiple times per pass through the smaller
  one, or shuffling doesn't ensure balanced exposure per step), so the
  effective training signal ratio at any given point is more skewed than
  the raw dataset size ratio suggests.

## Diagnose

1. Track validation metrics separately per task/domain throughout
   training, not just an aggregate metric -- plot each task's curve
   independently to see whether one is stagnant or regressing while the
   aggregate looks like it's improving.
2. Check the actual example count and per-step sampling ratio for each
   task in the training mixture, and compare that ratio to the intended
   or ideal balance for the business/product goal.
3. Compare per-task loss magnitudes early in training -- if one task's
   loss is consistently much larger in absolute terms, it will dominate
   gradient updates under naive loss summation even at equal sampling
   rates.
4. Train a single-task baseline on just the secondary task's data alone
   and compare its performance against the jointly-trained model's
   performance on that same task, quantifying exactly how much the joint
   training cost that task.

## Fix

Make task balance a deliberate, tunable part of the training recipe
rather than an incidental outcome of dataset sizes. Use explicit
per-task sampling weights (oversampling the smaller/harder task, or
capping the dominant task's per-epoch exposure) so the effective gradient
contribution ratio matches the intended priority, not the raw data ratio.
Normalize or weight per-task loss terms so differences in natural loss
scale don't implicitly determine priority. Track per-task validation
metrics as a first-class part of the training loop from the start, so
imbalance is visible during training rather than discovered afterward.
Where capacity is genuinely limited (e.g., a small LoRA rank), consider
increasing capacity or using task-specific adapters/heads on a shared
backbone instead of forcing both tasks through the same limited additional
parameters.

## Pitfalls

Don't fix this purely by oversampling the secondary task to equal
frequency without checking downstream effect on the dominant task -- overs
correcting can flip the imbalance the other direction, degrading the
originally-strong task, so per-task balance should be tuned iteratively
against both tasks' validation curves, not adjusted once and assumed
correct.

## Verify

Retrain with adjusted task weighting and confirm via per-task validation
tracking that the secondary task now shows meaningful improvement over its
pre-fix trajectory, while confirming the dominant task's performance
hasn't regressed below an acceptable threshold relative to its
single-task baseline. Compare both tasks' jointly-trained performance
against their respective single-task baselines to quantify the actual
tradeoff being made.
