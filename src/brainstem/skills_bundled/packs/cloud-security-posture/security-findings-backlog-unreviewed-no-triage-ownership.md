---
name: security-findings-backlog-unreviewed-no-triage-ownership
description: A cloud-native security posture tool accumulates thousands of unreviewed findings over time because no team has clear ownership of triaging and acting on them.
triggers: ["security dashboard has thousands of open findings", "nobody is assigned to fix these misconfigurations", "posture tool findings just pile up", "who owns remediating these alerts"]
permissions: ["READ"]
---

## Symptom

The native security posture tool (AWS Security Hub, GCP Security Command
Center, Azure Defender for Cloud, or a third-party CNAPP) shows a large
and growing count of open findings, many months or years old. The tool
is correctly detecting real misconfigurations, but the findings queue
functions as a graveyard -- nobody is assigned to review new findings as
they arrive, and there's no process that turns a finding into a tracked
remediation task.

## Likely causes

- **The tool was deployed to satisfy a compliance checkbox** (turn on
  the security posture service) without a corresponding operational
  process defining who reviews its output on an ongoing basis --
  detection was treated as the deliverable, not remediation.
- **Findings are routed to a generic security team inbox with no
  per-resource-owner mapping**, so the team that could actually fix a
  given finding (the team that owns the resource) never sees it, and the
  security team lacks the context or access to fix it themselves at
  scale.
- **No severity/exploitability-based triage exists**, so the queue mixes
  critical internet-facing exposures with low-risk internal
  misconfigurations in one undifferentiated list, and the sheer volume
  makes it feel unapproachable, so nobody starts.
- **There's no feedback loop or SLA tied to findings** (no target time-
  to-remediate, no escalation when a critical finding ages past a
  threshold), so findings that do get noticed have no forcing function
  to actually get fixed versus staying open indefinitely.

## Diagnose

1. Pull the current finding count broken down by severity and by age,
   and specifically check what fraction of critical/high findings are
   older than a reasonable remediation SLA (e.g. 30 days) -- this
   quantifies the actual scale of the backlog problem, not just its
   existence.
2. Check whether findings carry any resource-owner or team tag/mapping
   that would let them route automatically to the right team, versus
   landing in one undifferentiated queue.
3. Check whether any documented process defines who reviews new findings,
   on what cadence, and what happens when a finding ages past a
   threshold -- absence of any written process, versus an ignored
   written process, points to different fixes.
4. Sample a handful of the oldest critical findings and manually verify
   they're still valid (not stale/already-fixed-but-not-closed) to
   distinguish "real unaddressed risk" from "tool hasn't re-scanned."

## Fix

Establish explicit ownership by mapping findings to the team that owns
the underlying resource (via tagging conventions enforced at resource
creation, or an asset inventory the posture tool can join against),
rather than routing everything to a central security team that lacks
context to fix most of it directly. Define a written triage SLA by
severity (e.g. critical findings triaged within 24 hours, remediated or
formally risk-accepted within a set window) with automatic escalation
when a finding ages past its SLA. Prioritize the backlog by actual
exploitability and exposure (see the related skill on findings
prioritization) rather than working it in raw chronological or count
order, and close out stale/invalid findings so the remaining queue
reflects real, current risk.

## Pitfalls

Don't respond to a large backlog by mass-suppressing or bulk-resolving
old findings to make the dashboard number look better -- if the
underlying misconfigurations weren't actually fixed, suppression just
recreates the original blind-spot problem this pack addresses, now with
false confidence that it was handled.

## Verify

Confirm every open critical/high finding has an assigned owning team and
an SLA due date. Track the finding backlog's age distribution over the
following month and confirm the median age of open critical findings is
trending down, not flat or increasing, and confirm newly created
findings get an owner assigned within the defined triage window.
