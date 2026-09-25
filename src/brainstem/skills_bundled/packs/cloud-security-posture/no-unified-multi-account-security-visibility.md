---
name: no-unified-multi-account-security-visibility
description: A misconfiguration sits unnoticed for months in one of many cloud accounts because no centralized dashboard or process continuously monitors security posture across all of them.
triggers: ["nobody was watching that subscription", "we have too many accounts to check individually", "this misconfig existed for months before anyone noticed", "need a single view across all our cloud accounts"]
permissions: ["READ"]
---

## Symptom

A serious misconfiguration -- an open security group, a public bucket, a
disabled logging setting -- is discovered to have existed for months in
one specific account or subscription out of dozens the organization
runs. Nobody was specifically responsible for watching that account;
security tooling exists but reports per-account, and no one had it
rolled up into a single view that would have surfaced the outlier.

## Likely causes

- **Each team/account owner is expected to monitor their own account's
  native security posture tool**, but there's no organizational rollup,
  so an account with less active ownership (a legacy project, a
  sandbox that became load-bearing, an account from an acquisition)
  simply has nobody looking at its findings at all.
- **A centralized security tool was deployed but not configured to
  automatically onboard new accounts/subscriptions**, so accounts
  created after the initial rollout are invisible to it by default,
  and there's no process that guarantees new accounts get added.
- **Multi-cloud or multi-organization structure means findings live in
  several different native tools** (one cloud's native posture service
  per provider, per organization) with no aggregation layer, so getting
  a true single view requires someone to manually check N different
  consoles, which in practice nobody does regularly.
- **Alerting exists but is undifferentiated and noisy across all
  accounts combined**, so a genuinely urgent finding in a low-traffic
  account gets buried in the same feed as routine low-severity findings
  from high-traffic accounts, and nobody has time to triage the whole
  feed.

## Diagnose

1. Enumerate every cloud account/subscription/project the organization
   actually owns (billing console, account factory / landing zone
   inventory, or the cloud provider's organization-level account list)
   and cross-reference it against the list of accounts actually
   reporting into the central security tool -- the gap is the blind
   spot.
2. For each account found in the gap, check whether it has any
   ownership record at all (a tagged owner, a team mapping) -- accounts
   with no clear owner are the highest-risk blind spots since even a
   manual check wouldn't happen.
3. Check the central tool's account-onboarding mechanism (auto-discovery
   via organization/management account integration versus manual
   per-account setup) to determine whether the gap is structural
   (new accounts never get added automatically) or just a one-time
   backlog.
4. Review whether the existing native per-account tools were actually
   generating findings for the specific misconfiguration that went
   unnoticed -- if they were, this is a visibility/aggregation problem;
   if they weren't, it's also a detection coverage problem.

## Fix

Deploy or configure the cloud provider's organization-level security
posture aggregation (AWS Security Hub with organization-wide
delegated administration, GCP Security Command Center at the
organization level, Azure Defender for Cloud with a management-group
scope) so every account under the organization root is automatically
included by default, with no manual per-account onboarding step
required for new accounts to appear. For genuinely multi-cloud estates,
add a cross-provider aggregation layer (a CNAPP tool or a centralized
SIEM ingesting each provider's native findings) so a single queue covers
all providers. Tie every account to an explicit owner in the account
inventory itself, and route findings by severity and exposure so
critical findings in low-traffic accounts get the same triage priority
as those in high-traffic ones.

## Pitfalls

Don't treat "we bought a CNAPP/central tool" as done once it's deployed
-- if new accounts aren't automatically enrolled as they're created
(via organization-level policy rather than a manual checklist item),
the exact same blind spot reappears for every account created after the
tool's initial rollout, just shifted to a different account.

## Verify

Confirm the count of accounts reporting into the central tool matches
the count of accounts in the authoritative billing/organization
inventory, with zero unaccounted-for accounts. Create a new test
account/subscription and confirm it appears in the central tool's
coverage automatically within the expected onboarding window, without
anyone manually registering it.
