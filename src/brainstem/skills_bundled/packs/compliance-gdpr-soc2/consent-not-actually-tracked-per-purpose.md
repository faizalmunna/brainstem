---
name: consent-not-actually-tracked-per-purpose
description: An application collects a single blanket consent checkbox for data processing, but GDPR requires granular, purpose-specific consent, and the system has no way to honor a user withdrawing consent for one purpose while keeping another.
triggers: ["consent not granular gdpr", "cannot withdraw consent for specific purpose", "single consent checkbox not compliant", "purpose specific consent missing"]
permissions: ["READ"]
---

## Symptom

A user requests to withdraw consent for a specific data use (marketing
emails, for instance) while continuing to use the core service -- but
the application only ever captured a single, blanket "I agree to data
processing" consent at signup, with no way to represent or honor
partial withdrawal, forcing an all-or-nothing choice that doesn't
actually satisfy what the user (or the regulation) is asking for.

## Likely causes

- **Consent was implemented as a single checkbox at signup** for
  simplicity, without modeling the actual distinct purposes data is used
  for (service delivery, marketing, analytics, third-party sharing),
  each of which GDPR requires to be independently consentable and
  withdrawable.
- **The application's data model has no concept of consent scoped to a
  purpose** -- there's a boolean "consented" flag on the user record, not
  a structured record of which specific processing purposes were
  consented to and when.
- **Downstream systems (a marketing platform, an analytics tool) receive
  user data without any mechanism to check or respect purpose-specific
  consent state**, so even if consent were tracked more granularly
  upstream, withdrawing it wouldn't actually stop the downstream use.
- **The original consent flow was designed by engineering without legal/
  privacy input on what granularity is actually required**, so the gap
  between what was built and what's required wasn't caught until an
  actual withdrawal request or an audit surfaced it.

## Diagnose

1. Enumerate the actual distinct purposes personal data is used for in
   the application (service delivery, marketing, analytics, third-party
   sharing, etc.).
2. Check the current consent data model for whether it can represent
   per-purpose consent state at all, or only a single blanket flag.
3. For each downstream system receiving user data, check whether it has
   any mechanism to respect a purpose-specific consent signal, or
   whether it receives and uses data unconditionally once received.
4. Review any actual withdrawal requests received so far for how they
   were handled in practice, to understand the real-world gap concretely.

## Fix

Redesign the consent data model to track consent per distinct purpose
(a structured record, not a single boolean), captured at the point each
purpose is actually introduced (not just a blanket checkbox at signup),
and allow independent withdrawal per purpose. Propagate purpose-specific
consent state to downstream systems so they can actually respect it --
stopping marketing sends specifically when marketing consent is
withdrawn, without needing to stop core service delivery. Involve legal/
privacy expertise in defining what purposes need distinct consent for
this specific application's actual data uses, rather than engineering
guessing at the right granularity alone.

## Pitfalls

Don't over-engineer consent granularity to an extreme (dozens of
hyper-specific purposes) that becomes confusing for users to manage and
operationally complex to honor correctly -- granularity should match
what's legally required and what users would actually find meaningful
to control independently, not maximized for its own sake.

## Verify

For a test user, withdraw consent for one specific purpose and confirm
the application and all relevant downstream systems stop that specific
processing while continuing others the user hasn't withdrawn consent
for. Confirm the consent state change is itself recorded with a
timestamp, satisfying the audit-trail requirement for demonstrating
consent was honored.
