---
name: prediction-confidence-scores-not-calibrated
description: A model's reported confidence scores don't actually reflect real-world correctness likelihood, so downstream logic that trusts high-confidence predictions makes poor decisions.
triggers: ["model confidence not calibrated", "high confidence predictions still wrong", "confidence score does not mean accuracy", "downstream logic trusting bad confidence scores"]
permissions: ["READ"]
---

## Symptom

Downstream application logic uses a model's reported confidence score to
make decisions (auto-approving high-confidence predictions, routing
low-confidence ones to human review), but investigation reveals the
confidence scores don't actually correlate well with real-world
correctness -- predictions marked "95% confident" are wrong far more
often than 5% of the time, or vice versa, undermining the whole
confidence-based decision logic.

## Likely causes

- **The model's raw output score (a softmax probability, for instance)
  is being used directly as if it were a calibrated confidence measure**,
  but many model architectures/training procedures produce systematically
  overconfident or underconfident raw scores that don't map directly to
  true probability of correctness without explicit calibration.
- **No calibration step (temperature scaling, isotonic regression, or a
  similar technique) was applied after training** to align the model's
  output scores with actual observed accuracy at each confidence level.
- **Calibration was performed once at training time but never
  re-validated after the model was retrained or after production data
  distribution shifted**, so calibration that was once accurate has
  drifted out of alignment along with everything else affected by data
  drift.
- **Confidence is being computed and used inconsistently across different
  parts of the system** (a threshold tuned against one definition of
  confidence, applied to scores computed slightly differently
  elsewhere), producing a mismatch even if the underlying model's
  calibration is otherwise fine.

## Diagnose

1. Plot a reliability diagram (predicted confidence versus observed
   accuracy, bucketed) using a sample of predictions with known ground
   truth, to visualize and quantify the actual calibration gap.
2. Check whether any calibration step exists in the model's training/
   post-processing pipeline, or whether raw model output is used directly
   as confidence.
3. If calibration was applied at some point, check when, and compare
   against how much production data distribution may have shifted since
   then.
4. Audit every place in the system that reads/uses the confidence score
   for consistency in how it's computed and interpreted.

## Fix

Apply an explicit calibration technique (temperature scaling is simple
and effective for many neural network classifiers; isotonic regression or
Platt scaling for other model types) using a held-out calibration
dataset, so the model's output scores are adjusted to actually reflect
observed accuracy at each confidence level. Re-validate and, if needed,
recalibrate periodically as part of the same cadence as model retraining
or drift monitoring, since calibration can degrade independently of raw
predictive accuracy. Ensure every downstream consumer of confidence
scores uses the same, consistently-computed calibrated value.

## Pitfalls

Don't assume calibration is a one-time fix that never needs revisiting --
it's just as susceptible to drift as the model's underlying accuracy, and
a calibration that was accurate at launch can become misleading over
time without anyone noticing unless it's actively monitored.

## Verify

Regenerate the reliability diagram after calibration and confirm
predicted confidence now closely tracks observed accuracy across
confidence buckets. Confirm downstream decision logic (auto-approval
thresholds, human-review routing) produces the expected outcome
distribution when tested against the newly calibrated scores.
