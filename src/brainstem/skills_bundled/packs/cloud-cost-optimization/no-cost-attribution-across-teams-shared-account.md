---
name: no-cost-attribution-across-teams-shared-account
description: Cloud spend cannot be attributed to specific teams or products sharing an account, making it impossible to identify which team's usage is actually driving cost growth.
triggers: ["cannot tell which team is driving cloud cost", "shared cloud account no cost attribution", "cost allocation tags missing", "which team owns this spend"]
permissions: ["READ"]
---

## Symptom

Total cloud spend is rising, and finance/engineering leadership wants to
know which team or product is responsible for the growth, but the
billing data can't answer that -- many resources aren't tagged with an
owning team, multiple teams share the same account/subscription, and the
bill is effectively one undifferentiated total.

## Likely causes

- **Resources were provisioned without a consistent, enforced tagging
  convention for team/project/cost-center**, so even where a tag exists
  on some resources, it's inconsistent enough that aggregate reporting by
  owner isn't reliable.
- **Multiple teams share a single cloud account/subscription** for
  historical or administrative simplicity reasons, with no sub-account,
  resource-group, or tagging structure that cleanly separates their
  usage.
- **Shared infrastructure (a common Kubernetes cluster, a shared
  database, a shared networking layer) serves multiple teams'
  workloads**, and its cost is inherently difficult to attribute
  precisely to individual teams without additional cost-allocation
  tooling or process.
- **No organizational owner is responsible for cost attribution/
  allocation as an ongoing practice**, so even if tagging was reasonably
  good at some point, enforcement lapses over time as new resources are
  added without the same discipline.

## Diagnose

1. Sample a representative set of resources across the account and check
   what fraction have a reliable, consistent team/owner tag versus none
   or an inconsistent one.
2. Identify which portions of spend are inherently shared infrastructure
   (not cleanly attributable to one team) versus genuinely team-specific
   resources that simply aren't tagged yet.
3. Check whether the cloud provider's account/organization structure
   (separate accounts/subscriptions per team, or a single shared one) is
   itself a structural barrier to attribution, independent of tagging
   discipline.
4. Check whether any tagging policy exists at all, and if so, whether
   it's enforced (blocking untagged resource creation) or merely advisory
   (documented but not enforced, and therefore frequently skipped).

## Fix

Establish and enforce a mandatory cost-allocation tagging policy
(team/project/cost-center) at resource-creation time via cloud policy
enforcement (not just documentation), so new resources are attributable
by default going forward. For existing untagged resources, run a
retroactive tagging effort prioritized by cost magnitude (tag the biggest
spend items first). For shared infrastructure that can't be cleanly
attributed per-resource, use a documented, agreed-upon allocation
methodology (proportional to usage metrics, or an agreed split) rather
than leaving it as an attribution gap. Where team boundaries are stable
and significant, consider separate accounts/subscriptions per team as a
structural solution that makes attribution automatic rather than
tag-dependent.

## Pitfalls

Don't retroactively tag resources with a best-guess owner without
verifying with the actual team, since incorrect attribution is worse
than no attribution for driving accountability -- it can misdirect cost-
reduction efforts at the wrong team. Also don't over-invest in perfectly
precise attribution for genuinely shared infrastructure where a
reasonable approximate allocation is good enough for the actual decision-
making purpose (identifying broad cost drivers, not down-to-the-cent
chargebacks).

## Verify

After implementing tagging enforcement, confirm a high percentage
(ideally near 100%) of new resources are created with correct
attribution tags, and confirm cost reports can now break down spend by
team/project with acceptable accuracy, enabling the original question
("which team is driving this cost growth") to actually be answered from
the data.
