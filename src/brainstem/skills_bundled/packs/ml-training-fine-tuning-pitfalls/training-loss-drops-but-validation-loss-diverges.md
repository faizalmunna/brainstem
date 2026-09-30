---
name: training-loss-drops-but-validation-loss-diverges
description: A model's training loss keeps improving smoothly while validation loss flattens then rises, the classic overfitting curve, but the regularization already applied hasn't actually fixed it.
triggers: ["training loss going down but validation loss going up", "model overfitting despite dropout", "val loss diverging from train loss", "classic overfitting curve"]
permissions: ["READ"]
---

## Symptom

Plotting loss curves shows training loss decreasing monotonically (often
toward near-zero) while validation loss decreases initially, bottoms out,
and then climbs back up as training continues -- the textbook overfitting
curve. Critically, the team has already added *some* regularization
(dropout, weight decay, or an early-stopping callback) and the curve still
looks this way, meaning the applied fix isn't addressing the actual root
cause.

## Likely causes

- **The regularization strength doesn't match the capacity/data-size
  mismatch** -- a small dropout rate or weak weight decay on a model that's
  drastically over-parameterized for the dataset size will barely move the
  curve; the fix was applied but at the wrong magnitude.
- **Early stopping is monitoring the wrong signal or has too much
  patience** -- if the patience window is large, training runs many epochs
  past the actual validation minimum before stopping, so the "fix" exists
  but doesn't trigger early enough to matter.
- **Data leakage or duplication between train and validation splits**
  masks the real generalization gap early on, so the curve looks fine
  initially and the divergence appears later when the model finally
  memorizes the non-duplicated portion of training data.
- **The validation set is too small or not representative** of the true
  data distribution, producing a noisy or systematically different loss
  curve that isn't actually measuring generalization the way the team
  assumes.
- **Regularization was added to the wrong layers** -- e.g., dropout only
  on a final classification head while the real memorization capacity is
  in a large backbone or embedding table that has none.

## Diagnose

1. Plot train and validation loss (and a task metric, not just loss) per
   epoch on the same chart, and identify the exact epoch where validation
   loss stops improving -- that's the point past which every additional
   epoch is actively hurting generalization.
2. Check the deployed regularization values directly (dropout rate, weight
   decay coefficient, early-stopping `patience`) against the model size and
   dataset size -- a dropout of 0.1 on a 100M-parameter model fine-tuned on
   5,000 examples is a magnitude mismatch, not a real fix.
3. Verify train/validation split integrity: hash or exact-match rows across
   splits to rule out duplicate or near-duplicate leakage inflating the
   apparent train-val gap's timing.
4. Recompute validation loss with a larger held-out sample or k-fold
   validation to check whether the observed curve shape is stable or an
   artifact of validation set size/noise.
5. Inspect where regularization is actually applied in the model definition
   (which layers have dropout/weight decay) versus where the parameter
   count actually lives.

## Fix

Treat overfitting as a capacity-vs-data problem, not a checkbox to tick.
Scale the regularization to the actual mismatch: increase dropout or weight
decay incrementally while re-plotting the curve after each change rather
than assuming one fixed value works universally, and confirm the
regularization is applied at the layers that hold the most capacity, not
just the output head. Tighten early stopping (`patience` set low enough to
stop within a few epochs of the true validation minimum) and always restore
the best-validation-loss checkpoint rather than the final-epoch checkpoint.
If the mismatch is severe, reduce effective model capacity (freeze more
layers during fine-tuning, use a smaller adapter/LoRA rank) or increase
effective data (augmentation, more labeled examples) instead of relying on
regularization alone to compensate for a fundamentally too-small dataset
for the chosen model size.

## Pitfalls

Don't chase the overfitting curve by cranking regularization to extreme
values (very high dropout, huge weight decay) without re-checking training
loss -- over-regularizing can suppress the symptom by making the model
underfit both splits, which looks like "the gap closed" but the model is
now simply worse everywhere, not actually generalizing better.

## Verify

After adjusting regularization/early stopping, retrain and confirm the
validation loss curve now plateaus or improves for a materially longer
number of epochs before diverging, and that the gap between best train
loss and best validation loss at the selected checkpoint has shrunk
compared to the original run. Confirm the improvement holds on a genuinely
held-out test set the tuning process never touched, not just the same
validation set used to pick the new hyperparameters.
