---
name: best-checkpoint-selected-on-training-loss-not-validation
description: The checkpointing or early-stopping logic saves the model with the lowest training loss instead of the lowest validation loss, so the "best" saved checkpoint is actually the most overfit one.
triggers: ["best checkpoint performs worse than an earlier one", "early stopping monitoring training loss", "saved model is overfit despite early stopping", "checkpoint selection picked worst model"]
permissions: ["READ"]
---

## Symptom

The training pipeline includes checkpointing and/or early stopping, and by
some measure the run "worked" -- a checkpoint was saved and marked as
best. But when that checkpoint is evaluated on held-out data or in
production, it underperforms an earlier checkpoint from the same run, or
underperforms what the training loss curve seemed to promise. Inspecting
the checkpointing config reveals it's monitoring training loss (or a
training-set metric) rather than validation loss, so "best" was defined as
"most fit to the training data," which is exactly the checkpoint most
likely to be overfit.

## Likely causes

- **The monitored metric in the checkpoint/early-stopping callback was
  left at a default or was copied from a different project's config**
  (e.g., a framework default of monitoring `loss` instead of `val_loss`)
  without the team verifying which split it actually points to.
- **No validation loop is run during training at all**, or it's run too
  infrequently, so training loss is the only signal available at
  checkpoint-save time even though the team's intent was to select on
  validation performance.
- **Validation loss is computed but logged separately from the
  checkpointing/early-stopping logic**, so it's visible on a dashboard but
  never actually wired into the save/stop decision -- a configuration gap
  between observability and control.
- **The distinction between training loss and validation loss was
  understood conceptually but the specific config key name in the training
  framework was ambiguous or easy to get wrong** (e.g., `monitor="loss"`
  silently resolving to training loss in some frameworks and validation
  loss in others depending on when the callback fires).

## Diagnose

1. Locate the exact checkpoint-saving or early-stopping configuration in
   the training code (the `monitor` argument, or equivalent) and confirm
   literally which metric name and which data loader it's tied to.
2. Compare the training loss curve and validation loss curve for the run
   and identify the epoch at which each was minimized -- if they differ
   and the saved "best" checkpoint corresponds to the training-loss minimum
   rather than the validation-loss minimum, that confirms the root cause.
3. Re-evaluate several saved checkpoints from the same run (if multiple
   were kept) against the validation set directly, independent of
   whatever the training pipeline marked as "best," to find which
   checkpoint is actually best by that measure.
4. Check whether validation loss is computed and logged at all during
   training -- if it's absent entirely, the pipeline has no way to select
   on it regardless of configuration.

## Fix

Explicitly configure checkpointing and early stopping to monitor a
validation-set metric, and verify this by checking which data loader feeds
that metric in the framework being used rather than trusting a
default or a plausible-looking argument name. Ensure a validation pass
actually runs at a frequency that makes early stopping meaningful (e.g.,
every epoch, not every 10) so the monitored signal is timely enough to act
on. Where multiple metrics matter (loss plus a task metric like F1), decide
explicitly which one drives checkpoint selection and document it, since
optimizing loss and optimizing a downstream metric can select different
checkpoints. Keep more than just the single "best" checkpoint when storage
allows, so a wrong monitor-metric choice can be corrected retroactively
without retraining.

## Pitfalls

Don't assume switching the monitor to validation loss alone is sufficient
if the validation set itself is small or unrepresentative -- a validation-
loss-based selection is only better than training-loss-based selection to
the extent the validation set actually estimates generalization, so a
tiny or biased validation split can still lead to a poor checkpoint choice
even after fixing the monitored metric.

## Verify

Rerun training with checkpointing/early-stopping explicitly monitoring
validation loss (or the intended task metric), confirm via logs that the
saved "best" checkpoint's epoch matches the actual validation-metric
minimum, and re-evaluate that checkpoint against a separate held-out test
set to confirm it outperforms both the training-loss-selected checkpoint
from the earlier run and the final-epoch checkpoint.
