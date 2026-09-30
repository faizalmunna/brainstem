---
name: ab-test-inference-cost-not-accounted-for
description: An A/B test comparing a new, more expensive model against a baseline drives inference costs far higher than expected because the traffic split and cost-per-request weren't modeled together.
triggers: ["ab test model cost spike", "champion challenger inference cost surprise", "model experiment unexpectedly expensive", "ab test compute budget exceeded"]
permissions: ["READ"]
---

## Symptom

Running an A/B test (or champion/challenger comparison) between a
baseline model and a new candidate model results in a much larger
increase in overall inference infrastructure cost than anticipated,
discovered only when the bill arrives rather than being planned for
ahead of the experiment.

## Likely causes

- **The candidate model is significantly more computationally expensive
  per request** (larger model, more expensive architecture, longer
  average generation length) than the baseline, and the cost-per-request
  difference wasn't calculated and multiplied by expected traffic volume
  before launching the test.
- **The experiment requires running both models simultaneously at
  meaningful traffic volume** (not just a tiny canary percentage) to
  reach statistical significance in a reasonable time, meaning both
  models' infrastructure costs are incurred concurrently for the
  duration of the test, not sequentially.
- **Autoscaling for the candidate model's serving infrastructure wasn't
  tuned/tested before the experiment**, so it may over-provision (a
  conservative safety margin sized without real traffic data) well
  beyond what's actually needed for its test-traffic share.
- **The experiment ran longer than originally planned** (to reach
  significance, or due to delayed analysis) without a corresponding
  reassessment of whether the ongoing cost was still justified relative
  to the value of continuing.

## Diagnose

1. Calculate the actual measured cost-per-request for both the baseline
   and candidate models under the real test traffic conditions, and
   compare against what was estimated (if anything was estimated) before
   the experiment launched.
2. Check the actual traffic split percentage and duration against what
   was originally planned, to identify whether cost overrun came from
   traffic share, unexpected per-request cost, unexpected duration, or a
   combination.
3. Review the candidate model's serving infrastructure configuration for
   over-provisioning relative to its actual test-traffic volume.
4. Check whether there was a pre-defined cost budget or checkpoint for
   the experiment, and whether it was being tracked during the
   experiment's run.

## Fix

Before launching any model A/B test involving different-cost models,
calculate and pre-approve an estimated total cost based on expected
traffic split, expected duration, and each model's actual measured cost-
per-request (from a small-scale pilot if not already known). Right-size
the candidate model's serving infrastructure based on its actual planned
traffic share rather than defaulting to full production-scale
provisioning. Set an explicit cost checkpoint/budget alert for ongoing
experiments so a run extending beyond its planned duration triggers a
reassessment rather than continuing to accrue cost silently.

## Pitfalls

Don't shut down a legitimate, valuable experiment abruptly the moment
cost exceeds initial estimate without assessing whether the experiment
is close to reaching a valuable conclusion -- balance cost control
against the real cost of an inconclusive, prematurely terminated test
that would need to be rerun.

## Verify

For the next model experiment, confirm a cost estimate is calculated and
approved before launch, and confirm actual cost tracking during the
experiment stays within an acceptable range of that estimate, with an
alert firing if it doesn't.
