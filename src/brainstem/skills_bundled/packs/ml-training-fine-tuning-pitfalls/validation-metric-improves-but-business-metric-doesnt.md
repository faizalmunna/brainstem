---
name: validation-metric-improves-but-business-metric-doesnt
description: A model's validation metric steadily improves during training and tuning, but the downstream business or product outcome it's supposed to serve doesn't improve when the model ships.
triggers: ["accuracy went up but conversion didn't improve", "model metrics improved but product outcome unchanged", "optimized the wrong metric during training", "offline metric doesn't match online results"]
permissions: ["READ"]
---

## Symptom

Across training runs and hyperparameter tuning, the tracked validation
metric (accuracy, F1, AUC, perplexity) shows clear, consistent improvement,
and the team ships the best-scoring model expecting a corresponding
improvement in the actual downstream outcome it's meant to serve (revenue,
user engagement, task completion, safety incident rate). The business
metric doesn't move, or moves in the wrong direction, despite the model
metric looking unambiguously better.

## Likely causes

- **The training/validation metric is a proxy that's only loosely
  correlated with the real objective** -- e.g., optimizing classification
  accuracy on a class-imbalanced problem where the business actually cares
  about recall on the rare, high-value class, and accuracy can improve
  while that recall stays flat or drops.

- **The metric optimizes for average-case performance while the business
  outcome depends on tail or worst-case behavior** (e.g., overall
  perplexity improves while the specific failure cases that drive user
  complaints or churn are unaffected or worsened).
- **The offline evaluation distribution doesn't match the population the
  business metric is measured over** -- the validation set may
  overrepresent easy or common cases relative to the real traffic mix
  where the business outcome is actually determined.
- **The chosen metric rewards a behavior that's technically correct but
  practically unhelpful** -- e.g., a summarization model's ROUGE score
  improves by producing outputs closer to reference text in wording, while
  actual user-perceived usefulness (the real business proxy) is unaffected
  or worse.
- **There's a lag or confound between model quality and the business
  metric** -- the business metric is also affected by other product changes
  shipped around the same time, making it hard to attribute (or rule out)
  the model's contribution at all.

## Diagnose

1. Write down explicitly what the validation metric measures and what the
   business metric measures, and check whether they can plausibly diverge
   -- e.g., verify whether the validation set's class balance or difficulty
   distribution matches real production traffic.
2. Segment the validation metric by subgroup or use case that maps to the
   actual business driver (e.g., recall specifically on the high-value
   segment) rather than only looking at the aggregate number that was
   optimized.
3. Run an offline analysis correlating per-example validation metric score
   against the actual business outcome for a sample where both are known
   (e.g., historical predictions with known downstream results), to check
   whether improvement on one has historically tracked improvement on the
   other at all.
4. If already shipped, run a controlled online comparison (A/B test) of
   the new model against the previous one, isolating it from other
   concurrent product changes, to determine whether the model itself is
   responsible for the flat business metric.

## Fix

Identify or construct a metric that's a closer proxy for the real business
outcome before optimizing further -- this might mean a different
aggregate metric (recall on a specific segment instead of overall
accuracy), a weighted metric that reflects the actual cost structure of
different error types, or a composite metric combining the model score
with known downstream correlates. Where a perfect proxy isn't available,
treat the current metric as a filter for candidate models (rule out
clearly bad ones) rather than the final decision criterion, and validate
top candidates with a proper online experiment before fully committing.
Build the validation set's distribution to match production traffic as
closely as feasible, including its natural class balance and difficulty
mix, rather than a curated or rebalanced set that inflates ease of
measurement at the cost of representativeness.

## Pitfalls

Don't respond to this gap by continuing to optimize the same proxy metric
harder (more epochs, more tuning) on the assumption that a large enough
improvement will eventually show up downstream -- if the metric is
fundamentally decoupled from the business outcome, further optimization
just produces a model that's better at the proxy and no better (or worse)
at what actually matters.

## Verify

After switching to a better-aligned metric or evaluation approach, confirm
via a controlled online test (not just offline re-evaluation) that model
improvements on the new metric correspond to measurable movement in the
actual business outcome, isolated from other concurrent changes. Establish
this metric-to-outcome correlation as an ongoing check for future model
iterations, not a one-time validation.
