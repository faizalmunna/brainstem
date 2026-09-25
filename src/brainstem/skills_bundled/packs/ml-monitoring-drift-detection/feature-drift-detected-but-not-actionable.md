---
name: feature-drift-detected-but-not-actionable
description: A drift detection system correctly flags that input feature distributions have shifted, but the alert provides no guidance on whether the drift actually matters or what to do about it.
triggers: ["drift alert not actionable", "feature drift detected but unclear impact", "too many drift alerts ignored", "drift monitoring noise no signal"]
permissions: ["READ"]
---

## Symptom

A drift detection system correctly identifies that one or more input
feature distributions have statistically shifted from the training
baseline and fires an alert -- but the alert doesn't indicate whether
this specific drift actually degrades model performance, leaving the
team unsure whether to act, and over time these alerts get ignored as
noise because acting on every one is impractical.

## Likely causes

- **Drift detection is applied uniformly to every feature with the same
  statistical test and threshold**, regardless of how sensitive the
  model's predictions actually are to each specific feature, so a
  feature the model barely relies on triggers the same alert severity as
  one it heavily depends on.
- **Statistical drift (a distribution shift) and performance-impacting
  drift (actually degrading predictions) are conflated as the same
  thing**, when in reality many distribution shifts have negligible
  impact on model output, and only a subset of "statistically
  significant" drift actually matters.
- **No mechanism connects drift alerts to actual model performance
  metrics**, so there's no way to correlate "this feature drifted" with
  "and here's the resulting accuracy impact," leaving the alert as an
  isolated, context-free signal.
- **Drift thresholds were set using a generic statistical significance
  level rather than calibrated against what magnitude of shift has
  historically correlated with real performance degradation** for this
  specific model.

## Diagnose

1. Review recent drift alerts and, for each, check whether a
   corresponding accuracy/performance change actually occurred around the
   same time (using whatever ground-truth-based or proxy performance
   monitoring exists).
2. Assess feature importance (via the model's own feature importance
   scores, or an ablation study) to identify which features the model's
   predictions are actually most sensitive to, versus which have low
   practical impact regardless of drift.
3. Review the current drift detection configuration for whether
   thresholds/sensitivity are uniform across all features or
   differentiated by actual importance.
4. Survey the team for how they currently respond to drift alerts, to
   confirm the "alert fatigue, ignored as noise" pattern concretely.

## Fix

Prioritize drift monitoring and alerting by feature importance -- apply
tighter thresholds and higher alert severity to features the model is
actually sensitive to, and looser thresholds (or monitoring-only, no
alert) to low-importance features. Where feasible, correlate drift
alerts with actual downstream performance impact (using available
ground-truth or proxy performance signals) so an alert can indicate not
just "this drifted" but "and here's the estimated/observed impact,"
making it clear whether action is warranted. Calibrate drift thresholds
using historical data on what magnitude of shift has actually correlated
with meaningful performance change for this specific model, rather than
a generic statistical default.

## Pitfalls

Don't respond to alert fatigue by simply raising every threshold to
reduce alert volume -- that risks missing genuinely important drift on
high-sensitivity features; the fix is differentiating by importance and
connecting to actual impact, not blanket desensitization.

## Verify

After reprioritizing, monitor the drift alerting system's actual alert
volume and confirm it's meaningfully reduced for low-importance features
while high-importance feature drift is still reliably caught. For a
newly fired high-priority alert, confirm the team can now assess actual
performance impact (via the added correlation) rather than facing the
same ambiguity as before.
