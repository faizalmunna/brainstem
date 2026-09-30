---
name: inconsistent-security-baseline-across-cloud-providers
description: The same security control is enforced in one cloud provider but silently missing in another because policies were written against only one provider's native tooling.
triggers: ["we're secure in AWS but not sure about GCP", "our security policy only covers one cloud", "same control exists in one provider but not replicated in the other", "multi-cloud posture is inconsistent between providers"]
permissions: ["READ"]
---

## Symptom

The organization runs workloads across two or more cloud providers, and
a security control that's reliably enforced in the provider the security
team is most familiar with (say, mandatory encryption, restricted public
access, or mandatory logging) turns out to have no equivalent enforcement
in a second, less-central provider -- often one adopted later, through
an acquisition, or by a single team working outside the main platform.
The gap isn't a technical impossibility; the equivalent control exists
in the second provider too, it was just never actually configured there.

## Likely causes

- **Security policy and automation were originally built for the first
  and primary provider**, and adding a second provider (through
  organic growth, an acquisition, or a team's independent choice) never
  triggered a corresponding review of whether the same policies were
  replicated there, since the policy-as-code tooling in use is often
  provider-specific and doesn't automatically extend.
- **The security team's expertise and tooling familiarity skews heavily
  toward one provider**, so reviews and audits naturally focus there,
  and the second provider gets treated as lower priority or "someone
  else's problem" even though it holds real production workloads.
- **Each provider's equivalent control has different names, defaults,
  and configuration surface** (e.g. a policy named and scoped one way in
  one provider's policy engine has a differently-scoped equivalent in
  another), so even a well-intentioned attempt to "match" the policy
  across providers can be subtly incomplete without someone doing a
  careful side-by-side mapping.
- **Governance/compliance reporting rolls up findings per-provider into
  separate reports** that different stakeholders review, so no single
  view ever forces the comparison "is this control enforced equally
  everywhere," and a gap in the less-reviewed report goes unnoticed.

## Diagnose

1. Build an explicit control-equivalence map: for each security baseline
   requirement (encryption at rest, no public storage by default, MFA
   enforcement, centralized audit logging, network egress restrictions),
   list the specific mechanism that enforces it in each cloud provider
   in use, and mark any cell where no mechanism is actually configured
   (not just "should exist" but confirmed configured and active).
2. For each provider, check the organization-level or management-group-
   level policy enforcement point (AWS Organizations SCPs, GCP
   organization policies, Azure Policy at the management group level)
   to see what's actually applied there versus assumed.
3. Sample a handful of resources in the less-central provider directly
   against the same posture checks used confidently in the primary
   provider, to get concrete evidence of the gap rather than relying on
   assumptions about parity.
4. Check whether the second provider's accounts/subscriptions are even
   included in whatever central visibility or reporting process exists
   (this often overlaps with the multi-account-visibility gap, but the
   specific angle here is policy parity, not just monitoring coverage).

## Fix

Treat the control-equivalence map as a living artifact, not a one-time
exercise: for every security baseline requirement, explicitly implement
and verify the equivalent enforcement mechanism in every provider in use,
using each provider's native policy engine at the organization/
management-group level so new accounts inherit it automatically rather
than depending on a per-account setup step. Where a unified
policy-as-code or CNAPP tool supports multi-cloud policy definitions,
prefer expressing the baseline once and deploying it consistently across
providers over maintaining entirely separate, provider-specific policy
sets that can drift apart in coverage. Assign explicit ownership for
each non-primary provider so it isn't implicitly deprioritized simply
because it's less familiar to the core security team.

## Pitfalls

Don't assume a control is equivalent across providers just because it
has a similarly-named policy or setting -- verify the actual scope and
default behavior of each provider's mechanism directly, since subtle
differences (what's covered by default, what requires explicit
enrollment, what the default deny/allow behavior is) are exactly where
gaps hide even when someone believed they'd already matched the
policies.

## Verify

Run the same posture check (e.g., "any publicly accessible storage")
against every provider in use and confirm consistent enforcement results
across all of them, not just the primary one. Provision a new test
account/subscription in each non-primary provider and confirm the full
security baseline is automatically applied without any manual per-
account configuration step.
