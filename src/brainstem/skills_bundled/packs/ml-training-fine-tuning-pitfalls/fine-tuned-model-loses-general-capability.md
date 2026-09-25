---
name: fine-tuned-model-loses-general-capability
description: Fine-tuning a pretrained model on a narrow new task makes it perform much worse on the original broader task it used to handle well, a case of catastrophic forgetting.
triggers: ["fine-tuned model forgot how to do X", "catastrophic forgetting after fine-tuning", "model regressed on original task after fine-tuning", "fine-tuning broke general performance"]
permissions: ["READ"]
---

## Symptom

After fine-tuning a pretrained model (an LLM, a vision backbone, etc.) on a
narrow, specialized dataset, the model now performs the new task well but
has measurably degraded on tasks or inputs it previously handled
competently -- general instruction-following gets worse, or a vision model
loses accuracy on classes not represented in the fine-tuning set. The team
only evaluated the new task before shipping and discovered the regression
from user reports or a later broad eval.

## Likely causes

- **Full fine-tuning with too high a learning rate or too many epochs**
  overwrites a large fraction of the pretrained weights, aggressively
  reshaping representations that were previously general-purpose toward
  the narrow task's distribution.
- **The fine-tuning dataset is narrow and homogeneous** (single domain,
  single format, single response style), so the model has no gradient
  signal reminding it that other domains/styles/tasks still exist, and it
  drifts entirely toward the new distribution.
- **No mechanism to preserve prior capability was used** -- no replay of
  original-task/general data mixed into fine-tuning, no regularization
  toward the base model's weights (e.g., KL penalty or weight-distance
  penalty), and no parameter-efficient method that naturally limits drift.
- **Evaluation before shipping only covered the new task**, so the
  regression on general capability was never measured until after
  deployment -- this is a measurement gap, not just a training mistake.
- **Catastrophic forgetting is worse with full fine-tuning of small
  models** relative to large ones, and worse when the new task's data
  distribution is very different from pretraining data (e.g., a narrow
  internal jargon-heavy dataset vs. general web text).

## Diagnose

1. Run the fine-tuned model against the *same* general-capability
   benchmark or eval set that was used (or should have been used) to
   validate the base model, and diff the scores directly against the base
   model's scores on that same eval.
2. Check what fraction of parameters were updated: full fine-tuning versus
   a parameter-efficient method (LoRA, adapters, prefix tuning) -- full
   fine-tuning has categorically higher forgetting risk.
3. Inspect the fine-tuning learning rate and epoch count relative to
   standard guidance for the model size; a learning rate copied from a
   from-scratch training recipe is often 10-100x too high for fine-tuning.
4. Check whether the fine-tuning dataset included any general/original-task
   examples at all, or was 100% narrow-task data with no replay mixture.
5. Compare intermediate checkpoints (if saved) across epochs against the
   general benchmark to identify the epoch where general capability began
   dropping, which usually precedes narrow-task performance saturating.

## Fix

Choose a fine-tuning approach that bounds how far the model can drift from
its pretrained state, matched to how much general capability must be
preserved. For most cases, prefer parameter-efficient fine-tuning (LoRA,
adapters) over full fine-tuning, since it constrains updates to a low-rank
subspace and leaves the base weights untouched. Mix a meaningful fraction
of general-task or original-domain examples into the fine-tuning set
(replay/rehearsal) so gradients continue reinforcing prior capability
alongside the new task. Where preserving specific prior behavior is
critical, add an explicit regularization term pulling fine-tuned weights or
output distributions toward the base model (an L2-to-base-weights penalty,
or a KL-divergence penalty between fine-tuned and base model output
distributions on a reference set). Use a conservative learning rate (often
an order of magnitude below from-scratch training) and short training
duration, checking general-capability eval at each checkpoint rather than
only at the end.

## Pitfalls

Don't assume parameter-efficient fine-tuning alone fully solves forgetting
-- a LoRA adapter trained for too many epochs at too high a rank on
narrow, repetitive data can still meaningfully shift the effective output
distribution and cause noticeable general-capability regression, especially
when the adapter is merged into the base weights afterward.

## Verify

Re-run the same general-capability benchmark suite used in diagnosis after
applying the fix and confirm the score gap versus the base model has
shrunk to an acceptable, explicitly-defined threshold (not just "looks
better"), while confirming narrow-task performance is still acceptable.
Track this general-capability benchmark as a permanent regression gate for
any future fine-tuning of the same model, not a one-time check.
