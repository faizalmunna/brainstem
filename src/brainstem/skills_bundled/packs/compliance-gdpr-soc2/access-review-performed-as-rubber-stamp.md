---
name: access-review-performed-as-rubber-stamp
description: A periodic user access review required for compliance is completed by managers clicking approve on every entry without actually verifying anyone's access is still appropriate.
triggers: ["access review rubber stamped", "quarterly access review not meaningful", "manager approved access without checking", "compliance access certification not real"]
permissions: ["READ"]
---

## Symptom

A required periodic access review (a SOC 2 or similar compliance control
requiring managers to periodically certify their team's system access is
still appropriate) is completed on schedule every cycle, satisfying the
compliance checkbox -- but investigation reveals managers are approving
every single access grant without actually checking whether it's still
needed, and stale/inappropriate access (a former team member's account,
an old elevated permission no longer required) persists through
multiple "completed" review cycles.

## Likely causes

- **The review process presents managers with a long list of
  access grants with no context about what each one actually means or
  why it might no longer be needed**, making genuine evaluation
  effortful compared to just clicking approve on everything.
- **No consequence or follow-up exists for a rubber-stamped review** --
  the compliance requirement is satisfied by the review being completed
  on time, regardless of whether it was done thoughtfully, so there's no
  feedback loop correcting the behavior.
- **Managers reviewing access don't actually have the context to judge
  appropriateness** (they don't know what a specific system permission
  actually grants, or whether a team member still needs it for their
  current role), so even a well-intentioned manager may not be equipped
  to review meaningfully.
- **The review cadence or volume is too high relative to actual access
  changes**, making most individual reviews genuinely redundant (nothing
  changed since last time) and training reviewers to treat the whole
  process as a formality.

## Diagnose

1. Sample recent completed access reviews and cross-reference against
   actual personnel changes (departures, role changes) during the same
   period to check whether any stale access was actually caught and
   revoked, versus everything being approved regardless.
2. Interview a few managers about how they actually approach the review
   -- how much time they spend, what information they use to decide,
   whether they understand what each permission actually grants.
3. Check whether the review tooling presents actionable context (last
   login date, what the permission is used for) or just a bare list of
   grants with no supporting information.
4. Check historical review outcomes for the rate of access actually
   revoked versus approved, across several cycles -- a rate near zero
   revocations across many cycles is a strong signal of rubber-stamping.

## Fix

Redesign the review process to surface actionable context per access
grant (last login/usage date, a plain-language description of what the
permission does, whether the grantee's role has changed since the
access was granted) so a meaningful decision is actually easier than a
reflexive approval. Pre-flag likely-stale grants (long-unused
permissions, access predating a known role change) for extra scrutiny
rather than presenting every grant with equal visual weight. Track and
report the actual revocation rate per review cycle as a leading
indicator of review quality, and follow up specifically with reviewers
showing a persistent zero-revocation pattern.

## Pitfalls

Don't respond by simply demanding managers "review more carefully"
without giving them better tooling/context -- that puts the burden on
individual diligence against a process that's still structurally hard to
do well, and won't durably change behavior.

## Verify

After improving the review tooling/process, track the revocation rate
across the next few cycles and confirm it's no longer consistently zero
(assuming genuine access changes have occurred in that period). Spot-
check a sample of the next cycle's reviews against actual personnel
records to confirm reviewers are correctly catching real staleness, not
just producing a different rubber-stamp pattern with better-looking
justifications.
