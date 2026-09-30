---
name: model-rollback-lacks-clear-trigger-criteria
description: A degraded model stays in production far longer than it should because no predefined, automated trigger exists for when monitoring signals should force a rollback to the previous version.
triggers: ["degraded model not rolled back", "no automated rollback trigger for model", "model performance decline unnoticed long time", "manual decision delayed model rollback"]
permissions: ["READ"]
---

## Symptom

A model's monitored performance metrics clearly show meaningful
degradation, but the model continues serving production traffic for an
extended period before anyone rolls it back to the previous, better-
performing version -- the delay isn't because degradation wasn't
detected, but because no predefined criteria or automated mechanism
existed to trigger a rollback decision promptly.

## Likely causes

- **Monitoring exists and correctly flags degradation, but rollback is a
  manual decision requiring someone to notice the alert, interpret it,
  and decide to act**, and this human-in-the-loop chain introduces delay,
  especially if the alert isn't treated with the urgency of an
  operational incident.
- **No explicit, pre-agreed threshold exists for "this level of
  degradation warrants an automatic or fast-tracked rollback"**, so each
  instance of degradation becomes a fresh, ad hoc judgment call about
  severity, consuming time that a predefined threshold would have saved.
- **Rolling back is technically more involved than it should be** (no
  one-command rollback mechanism, requires redeploying infrastructure)
  making the rollback decision feel more costly/risky than it should be,
  biasing toward waiting and hoping the metric recovers on its own.
- **Ownership for acting on model performance alerts isn't clearly
  assigned**, so an alert can fire without a specific person or team
  feeling responsible for acting on it promptly, unlike a clearly-owned
  operational incident.

## Diagnose

1. Reconstruct the timeline from when degradation was first detectable in
   monitoring to when rollback actually occurred, identifying which
   specific stage (detection, escalation, decision, execution) consumed
   the most time.
2. Check whether any predefined rollback threshold/criteria exist in
   documentation, or whether the decision was made fully ad hoc.
3. Check the actual technical mechanism for rolling back a model version
   and measure how long execution itself takes once a decision is made.
4. Check whether ownership for model performance alerts is explicitly
   assigned to a specific person/team with clear escalation expectations.

## Fix

Define explicit, quantitative rollback trigger criteria in advance (a
specific accuracy/error-rate threshold, sustained for a specific
duration) so a rollback decision doesn't require ad hoc judgment under
pressure each time. Where the criteria are clear and low-risk enough,
implement automated rollback (reverting to the previous model version
without waiting for human approval) for the most severe, unambiguous
degradation cases, reserving human judgment for more ambiguous scenarios.
Build a fast, low-friction rollback mechanism (a single command or
automated pipeline step) so execution time isn't itself a source of
delay once a decision is made. Assign clear ownership for model
performance alerts with the same urgency expectations as operational
incident response.

## Pitfalls

Don't set automated rollback thresholds so sensitive that normal metric
noise triggers unnecessary rollbacks -- validate thresholds against
historical metric variance to distinguish real degradation from routine
fluctuation before enabling automatic action.

## Verify

Simulate a clear degradation scenario in a non-production environment
and confirm the defined trigger criteria correctly identify it and
either automatically initiate rollback or promptly alert the responsible
owner. Measure end-to-end time from simulated degradation to completed
rollback and confirm it's meaningfully faster than the historical
incident that prompted this fix.
