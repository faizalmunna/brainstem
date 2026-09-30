---
name: unmeasured-inter-annotator-disagreement-in-labels
description: A model trained on human-labeled data plateaus at a mediocre ceiling because inconsistent labeling between annotators was never measured or reconciled.
triggers: ["model can't get past a certain accuracy ceiling", "labels look inconsistent between annotators", "annotator agreement never measured", "noisy ground truth labels"]
permissions: ["READ"]
---

## Symptom

Model performance plateaus well below what the task seems to warrant --
error analysis shows many "wrong" predictions that, on closer inspection
of the specific example, look like defensible or even correct answers
that simply disagree with the recorded ground-truth label, and different
model architectures or more data don't move the ceiling because the
limiting factor is the labels themselves, not the model.

## Likely causes

- **Multiple annotators labeled the dataset with no measured agreement
  rate (no Cohen's kappa, no Krippendorff's alpha, no periodic
  adjudication)**, so a systematic ambiguity in the labeling guidelines
  produces genuinely inconsistent ground truth that no model can learn a
  single consistent function from.
- **Labeling instructions were ambiguous or under-specified for edge
  cases** (e.g., how to label a borderline sentiment, a partially visible
  object, a transaction that's ambiguous between two fraud categories),
  and different annotators resolved the ambiguity differently without
  anyone noticing because there was no adjudication step.
- **Annotator drift over time** -- labeling guidelines were clarified or
  annotators gained experience partway through a large labeling effort,
  so labels from early batches are systematically different from labels
  from later batches even though nominally following "the same"
  instructions.
- **A single annotator per example was used with no spot-checking or
  second-pass review**, so individual annotator bias or fatigue-driven
  errors go directly into the training set undetected, with no mechanism
  to catch them.

## Diagnose

1. If any examples have multiple independent labels, compute an
   inter-annotator agreement statistic (Cohen's kappa for two annotators,
   Krippendorff's alpha or Fleiss' kappa for more) and check whether it
   falls below an acceptable threshold (kappa below roughly 0.6 is
   generally considered troubling, but compare against what similar tasks
   in the literature achieve).
2. If most examples have only a single label, pull a random sample and
   have a second annotator (or the same annotator blind to their
   original answer) re-label it; measure disagreement on that sample as
   a proxy for the whole dataset.
3. Break agreement/disagreement down by label class and by annotator --
   look for a class or a specific annotator that drives most of the
   disagreement, which points to a guideline ambiguity or a single
   problem labeler respectively rather than a systemic issue.
4. Check labeling timestamps against any guideline revision history to
   test for annotator drift across labeling batches.

## Fix

Establish a labeling process that measures agreement as a first-class
output, not an afterthought: label a meaningful fraction of examples with
multiple annotators, compute agreement statistics per batch, and route
disagreements to an adjudication step (a senior labeler or the task
owner makes the final call) rather than picking one annotator's answer
arbitrarily or averaging. Where agreement is structurally low because the
task itself is ambiguous, revise the labeling guidelines with explicit
examples for the disputed edge cases and re-label the affected subset,
rather than training on labels everyone privately knows are inconsistent.

## Pitfalls

Don't treat low inter-annotator agreement as something to paper over by
simply adding more labeled data from the same ambiguous process -- more
noisy labels don't raise the achievable ceiling, and teams that respond
to a plateau by scaling up labeling volume rather than labeling quality
often spend significant budget without moving the metric.

## Verify

After clarifying guidelines and re-labeling the disputed subset,
recompute inter-annotator agreement on a fresh multi-annotator sample and
confirm it has measurably improved. Retrain on the reconciled labels and
confirm the model's error analysis shows fewer "arguably correct"
predictions being penalized, and that the previous performance ceiling
has moved.
