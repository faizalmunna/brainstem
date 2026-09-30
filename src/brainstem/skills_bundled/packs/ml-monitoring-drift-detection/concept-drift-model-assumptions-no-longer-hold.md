---
name: concept-drift-model-assumptions-no-longer-hold
description: A model's accuracy degrades even though input feature distributions look unchanged, because the underlying relationship between features and outcome has shifted (concept drift) rather than the inputs themselves.
triggers: ["concept drift model accuracy dropped", "relationship between features and outcome changed", "model degraded without input distribution change", "underlying pattern shifted not the data"]
permissions: ["READ"]
---

## Symptom

A model's prediction accuracy degrades over time, but input feature
distribution monitoring shows no significant shift -- the features
themselves look statistically similar to the training distribution, yet
the model is performing worse, pointing at concept drift (the actual
relationship between inputs and the correct outcome has changed) rather
than data/covariate drift (the inputs themselves changing).

## Likely causes

- **An external, real-world change altered what outcome actually follows
  from a given set of input features** (a change in user behavior, a
  market shift, a new competitor, a policy/regulatory change) that the
  model has no way to detect from input distributions alone, since the
  inputs look the same but what they now predict has changed.
- **A previously stable seasonal or cyclical pattern the model implicitly
  learned has shifted or ended**, and the model continues applying
  outdated seasonal assumptions to current data.
- **The model was trained on data from before a significant product or
  business process change** (a new feature launched, a pricing change, a
  UX redesign) that altered user behavior patterns in a way not
  reflected in the training data's feature-outcome relationships.
- **Feature drift detection alone is fundamentally blind to concept
  drift** since it only compares input distributions, not the
  feature-to-outcome relationship, so relying solely on feature drift
  monitoring gives false confidence when concept drift is the actual
  cause.

## Diagnose

1. Confirm feature/input distribution monitoring genuinely shows no
   significant shift during the period accuracy degraded, ruling out
   ordinary covariate drift as the primary cause.
2. Where ground truth is available (even delayed), analyze whether the
   model's errors have a specific pattern -- systematically wrong in one
   direction, concentrated in a specific segment -- that might point to
   what changed in the real world.
3. Investigate known external changes (business process, market,
   competitive, seasonal, regulatory) around the time degradation began,
   correlating timing with the performance decline.
4. If feasible, train a fresh model on only the most recent data and
   compare its behavior/predictions against the existing model on the
   same current inputs, to see if the relationship it learns has
   genuinely shifted.

## Fix

Retrain the model on more recent data that reflects the current
feature-outcome relationship, since concept drift generally can't be
fixed by adjusting for input distribution alone -- the model needs to
relearn the new pattern. Establish a regular retraining cadence
(informed by how quickly concept drift tends to occur for this specific
domain) rather than only retraining reactively after a problem is
noticed. Where the underlying real-world change is understood and
significant, consider whether the model's feature set itself needs to
change to capture the new relevant signal (a new feature reflecting the
external change) rather than just retraining with the same features on
newer data.

## Pitfalls

Don't assume retraining on recent data alone always fully solves concept
drift -- if the drift is severe enough (a fundamental shift in what
drives the outcome), even a model retrained on recent data may need
architectural or feature-set changes, not just fresh parameters on the
same structure.

## Verify

After retraining, measure accuracy on a genuinely held-out, most-recent
period (data the retrained model hasn't seen) and confirm it recovers to
an acceptable level. Establish ongoing performance monitoring (via
ground truth or a reliable proxy) specifically to catch the next
instance of concept drift earlier than this one was caught.
