---
name: infrastructure-config-drifted-from-iac-baseline
description: Live cloud infrastructure no longer matches its documented infrastructure-as-code baseline because manual console changes accumulated unnoticed.
triggers: ["terraform plan shows unexpected changes we didn't make", "console config doesn't match our IaC", "security setting was changed manually and never reverted", "our documented baseline is out of date with reality"]
permissions: ["READ"]
---

## Symptom

Running a plan/diff against the infrastructure-as-code definition for an
environment shows a long list of unexpected changes -- resources whose
live configuration doesn't match what the code says it should be. Nobody
recalls submitting those changes through the normal review process; they
accumulated from ad hoc console edits made during incidents, demos, or
"quick fixes" over months, and some of them are security-relevant
(a security group rule, an encryption setting, a public-access flag).

## Likely causes

- **An incident response required an emergency console change to
  mitigate an active problem**, and the follow-up task to reconcile that
  change back into the IaC source was never completed once the incident
  was resolved and attention moved elsewhere.
- **Engineers with console access make small "harmless" tweaks outside
  the IaC pipeline** (adjusting a timeout, adding a tag, opening a port
  for a debugging session) because it's faster than a full PR-review-
  apply cycle, treating IaC as a starting point rather than the
  continuously enforced source of truth.
- **The IaC pipeline itself only runs on a schedule or on merge to main**,
  so there's a window between when a manual change happens and when the
  next apply would have caught and reverted it -- and if that next apply
  is skipped or fails, drift persists indefinitely.
- **Multiple tools manage overlapping resources** (Terraform and a
  separate ClickOps-driven security team process, or two different IaC
  stacks touching the same account) and each assumes it owns the
  resource's full configuration, so one tool's apply gets silently
  undone by the other's next run or vice versa.

## Diagnose

1. Run a read-only drift-detection pass (`terraform plan` against
   current state without applying, or an equivalent for the IaC tool in
   use) across every stack managing the environment, and capture the
   full diff rather than skimming for anything that looks alarming.
2. For each drifted resource, check the provider's activity/audit log
   (AWS CloudTrail, GCP Cloud Audit Logs, Azure Activity Log) for the
   specific change event, its actor, and timestamp, to determine whether
   it was a console change, a separate automation, or an out-of-band API
   call.
3. Classify each drifted item by security relevance -- flag anything
   touching network ingress rules, encryption settings, public-access
   flags, or IAM bindings as high priority, separate from cosmetic drift
   like tags or descriptions.
4. Check whether the IaC pipeline has any state-locking or continuous
   drift-detection job already configured and, if so, why it didn't
   catch or alert on this drift already (schedule too infrequent,
   alerting not wired to a channel anyone watches).

## Fix

For each drifted resource, decide deliberately whether the live state or
the IaC definition is correct, rather than blindly reverting to code --
some drift represents a legitimate change that should be imported back
into the IaC source. Import legitimate changes into the code through the
normal review process; revert illegitimate/forgotten changes by applying
the existing IaC. Then close the structural gap: enable scheduled,
automated drift detection (not just on-merge applies) that runs
regularly and posts findings somewhere the team actually reviews, and
restrict direct console write access for security-relevant resource
types to a documented break-glass process so manual changes become the
rare, tracked exception instead of the routine path.

## Pitfalls

Don't resolve drift by always running `apply` to force everything back
to the code's last-known state without inspecting what changed first --
if the manual change was a legitimate emergency mitigation that's still
needed, blindly reverting it can reintroduce the original incident.
Always classify and understand each drifted item before choosing
revert-to-code versus import-into-code.

## Verify

Re-run the drift-detection plan immediately after reconciliation and
confirm it reports zero unexpected differences. Confirm the scheduled
drift-detection job is actually enabled and its next run is on the
calendar, then deliberately make one test manual change in a
non-production environment and confirm the job detects and alerts on it
within its expected cadence.
