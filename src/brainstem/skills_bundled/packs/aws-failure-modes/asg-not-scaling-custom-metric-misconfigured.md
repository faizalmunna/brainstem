---
name: asg-not-scaling-custom-metric-misconfigured
description: An Auto Scaling Group fails to scale out under real load because its custom CloudWatch metric or alarm statistic never actually crosses the configured threshold.
triggers: ["auto scaling group not scaling up", "asg scaling policy not triggering", "cloudwatch alarm never breaches threshold", "custom metric scaling not working", "asg stuck at minimum capacity under load"]
permissions: ["READ"]
---

## Symptom
An Auto Scaling Group is clearly under real load (application-level
latency degrades, queue depth grows, error rates rise) but never scales
out beyond its minimum/current capacity -- the associated CloudWatch
alarm driving the scaling policy stays in `OK` state (or flaps without
sustaining `ALARM`), even though the underlying condition it's supposed
to detect is, by every other observable signal, clearly true.

## Likely causes
1. **The alarm's statistic doesn't match the metric's actual behavior**
   -- e.g., an alarm on `Average` CPU utilization across the group can
   stay comfortably below threshold even while individual instances are
   pegged, if load is unevenly distributed; the average smooths out
   exactly the signal the alarm was meant to catch.
2. **The custom metric is being published with dimensions that don't
   match what the alarm is actually watching** -- a metric published
   per-instance or per-host, while the alarm expects an aggregate
   (or vice versa), means the alarm is evaluating a metric stream that
   is sparse, always-zero, or entirely separate from the data actually
   being emitted.
3. **The metric's publishing interval or the alarm's evaluation period is
   mismatched**, so a metric published every 5 minutes evaluated by an
   alarm with a 1-minute period sees mostly missing data points, and
   depending on the alarm's "missing data" treatment (`missing`,
   `notBreaching`, `ignore`, `breaching`), gaps can silently prevent the
   alarm from ever accumulating enough consecutive breaching
   datapoints to fire.
4. **The scaling policy's target value or threshold was set based on a
   different unit or scale than what the metric actually reports** --
   e.g., a metric reporting a ratio (0.0-1.0) evaluated against a
   threshold written assuming a percentage (0-100), so real values never
   get anywhere near the configured number.
5. **The metric math expression (for alarms built on `metrics` math,
   e.g., combining request count and instance count into a per-instance
   rate) has an error in the expression itself** -- a divide-by-zero
   guard that always returns a low sentinel value, or a mismatched time
   alignment between the two source metrics being combined, silently
   producing an output that never reflects real load.

## Diagnose
- Graph the exact metric and statistic the alarm uses (not a similar-
  looking dashboard metric) over the incident window, and overlay the
  alarm's threshold line -- this immediately shows whether the metric
  itself ever approached the threshold, separate from whether the
  scaling policy or ASG configuration is at fault.
- Check `aws cloudwatch describe-alarms` for the exact `Statistic`,
  `Period`, `EvaluationPeriods`, `DatapointsToAlarm`, and
  `TreatMissingData` settings, and cross-check the `Statistic` choice
  against known load distribution (uneven vs. even across instances).
- For custom metrics, run `aws cloudwatch list-metrics` filtered to the
  expected namespace/metric name and inspect the actual `Dimensions`
  being published versus what the alarm specifies -- a dimension
  mismatch means the alarm is watching an empty or wrong series.
- For metric math alarms, evaluate the expression's components
  independently first (graph each raw input metric alone) before
  trusting the combined expression, to isolate whether one input is
  wrong or the math itself is wrong.
- Check the alarm's history (`describe-alarm-history`) for
  `StateUpdatePending`/`InsufficientData` transitions, which point at a
  missing-data problem rather than a genuinely-not-breaching metric.

## Fix
Choose a statistic that actually reflects the condition meant to trigger
scaling -- `Maximum` or a percentile (`p90`/`p99`) across the group
catches uneven hot-instance load that `Average` would mask, while
`Average` remains appropriate for genuinely uniform load. Ensure the
custom metric's publish dimensions exactly match what the alarm consumes,
and prefer publishing an already-aggregated metric (e.g., one value
representing the whole ASG) when the alarm is meant to reflect
group-wide state, rather than relying on CloudWatch to aggregate
per-instance dimensions the alarm wasn't actually configured to combine.
Align the metric's publish interval with the alarm's evaluation period
(or make the alarm's period a multiple of the publish interval with
`TreatMissingData` set deliberately, e.g., `missing` treated as
`notBreaching` only if that's actually the safe default for this alarm).
Verify the threshold's unit/scale assumption against a real sample of
the metric's actual reported values before trusting a threshold copied
from documentation or a different metric.

## Pitfalls
Fixing an unresponsive alarm by drastically lowering the threshold until
it fires "eventually" can cause premature or flapping scale-out on normal
load variance instead of fixing the actual mismatch (wrong statistic,
wrong dimensions, wrong units) -- lowering the threshold treats the
symptom, not the misconfiguration. Also, switching `TreatMissingData` to
`breaching` as a blunt fix for a gappy metric can cause scale-out storms
during unrelated metric publishing outages, since any gap now counts as
a breach regardless of real load.

## Verify
After correcting the statistic/dimensions/threshold, generate a
controlled load test that's known to represent real scaling-worthy
conditions, and confirm the CloudWatch alarm transitions to `ALARM`
state within the expected number of evaluation periods, and that the
ASG's activity history (`describe-scaling-activities`) shows a
corresponding scale-out action triggered by that alarm.
