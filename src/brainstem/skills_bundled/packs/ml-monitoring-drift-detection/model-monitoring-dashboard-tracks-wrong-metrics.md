---
name: model-monitoring-dashboard-tracks-wrong-metrics
description: A model monitoring dashboard tracks generic ML metrics (accuracy, F1) that look healthy while the business outcome the model was actually built to improve continues to decline.
triggers: ["model metrics good but business outcome bad", "monitoring dashboard tracking wrong thing", "accuracy fine but real impact declining", "ml metrics disconnected from business kpi"]
permissions: ["READ"]
---

## Symptom

A model's monitoring dashboard shows healthy, stable values for standard
ML metrics (accuracy, precision/recall, F1 score) over an extended
period, but the actual business outcome the model was deployed to
improve (conversion rate, fraud losses, customer retention) has been
declining, and nobody noticed because the dashboard everyone watches
doesn't track that outcome directly.

## Likely causes

- **The monitoring dashboard was built around metrics that are easy to
  compute from the model's own predictions and available ground truth**,
  which don't necessarily correspond to the actual business metric the
  model was built to move, especially if the relationship between the
  two isn't one-to-one.
- **The business metric requires joining model prediction data with data
  from other systems** (a downstream conversion event, a financial
  outcome) that wasn't set up as part of the model monitoring
  infrastructure, making the ML-native metrics the path of least
  resistance even if they're not the metrics that actually matter.
- **A model performing well on its trained objective can still fail to
  move the business metric** if the trained objective was an imperfect
  proxy for the actual business goal from the start (a classic
  proxy-metric misalignment), and monitoring only the proxy hides this
  gap entirely.
- **Ownership of ML metric monitoring and business metric monitoring sits
  with different teams/dashboards**, so nobody has a single view
  connecting the two, and a decline in the business metric doesn't
  automatically prompt anyone to check whether it's model-related.

## Diagnose

1. Identify the actual business metric the model was deployed to improve
   and check its historical trend independently of the ML monitoring
   dashboard.
2. If the business metric has declined while ML metrics look stable,
   investigate whether the relationship between the model's predictions
   and the business outcome has changed (a downstream process change, a
   shift in how predictions are actually used/acted upon) even if the
   model's raw prediction quality hasn't.
3. Check whether the data needed to compute the business metric alongside
   model predictions is actually available and joined anywhere, or
   whether it exists only in a separate system nobody connects back to
   model monitoring.
4. Review who owns monitoring for each metric and whether any process
   exists to correlate a business metric decline with a potential model
   cause.

## Fix

Build monitoring that tracks the actual business outcome metric
alongside (not instead of) standard ML metrics, joining model prediction
data with whatever downstream system holds the true outcome. Establish
clear ownership connecting model monitoring and business metric
monitoring, so a decline in the business metric routinely triggers a
check against model-related causes rather than being investigated in
isolation by a different team unaware of the model's existence.
Periodically re-validate that the model's trained objective still
correlates well with the actual business goal, since that relationship
itself can drift even when the model's own prediction quality is stable.

## Pitfalls

Don't over-index the model monitoring dashboard on the business metric to
the exclusion of ML-native metrics -- the business metric can be affected
by many factors outside the model's control (other product changes,
market conditions), so ML-native metrics remain valuable for isolating
whether the model specifically is the cause of an observed business
change.

## Verify

Confirm the new dashboard displays both the business outcome metric and
standard ML metrics together, with a visible historical trend for both.
Test the new joined-data pipeline by confirming it correctly reflects a
known historical period where both metrics changed, validating the join
logic is accurate.
