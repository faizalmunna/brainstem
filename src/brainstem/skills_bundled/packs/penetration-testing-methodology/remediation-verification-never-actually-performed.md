---
name: remediation-verification-never-actually-performed
description: A penetration test finding is marked as remediated based on the development team's own claim, with no independent retest confirming the fix actually closed the vulnerability.
triggers: ["remediation never verified", "fix marked done but not retested", "pentest finding closed without confirmation", "vulnerability reopened after being marked fixed"]
permissions: ["READ"]
---

## Symptom

A vulnerability identified in a penetration test is marked as
"remediated" in tracking based on the responsible team reporting that
they fixed it, but no independent retest was ever performed to confirm
the fix actually works -- and the same vulnerability is later
rediscovered (in a follow-up test, or worse, in a real incident),
revealing the original fix was incomplete or ineffective.

## Likely causes

- **No retest phase was budgeted or scheduled as part of the original
  engagement**, treating the report delivery as the end of the
  engagement rather than including a verification step for fixed
  findings.
- **The development team's fix addressed the specific proof-of-concept
  used to demonstrate the vulnerability but not the underlying root
  cause**, so a slightly different exploitation approach against the
  same underlying flaw still succeeds, and nobody tested for that
  variant.
- **Tracking systems mark findings "resolved" based on a status update
  from the responsible team with no required evidence or independent
  check attached**, making it easy for an incomplete fix to be marked
  complete based on good-faith but unverified belief.
- **Time/budget pressure deprioritized retesting** in favor of moving on
  to the next engagement, treating verification as a lower-priority
  activity than finding new issues.

## Diagnose

1. Review the vulnerability tracking system for what evidence (if any)
   was required to mark each finding as remediated -- a code diff link,
   an independent retest result, or just a status change with no
   attached evidence.
2. For a specific rediscovered vulnerability, compare the original
   report's proof-of-concept against the fix that was implemented, to
   determine whether the fix addressed the root cause or only the
   specific demonstrated exploitation path.
3. Check whether the original engagement's scope/contract included a
   retest phase at all, and if so, why it wasn't executed for this
   finding.
4. Review historical remediation-verification rates across past
   engagements to determine whether this is a one-off gap or a
   systemic process issue.

## Fix

Include an explicit retest phase in the scope of every penetration
testing engagement (or as a follow-up engagement) specifically to
verify remediated findings, treating verification as a required, budgeted
part of the process rather than optional follow-up. Require actual
evidence (an independent retest result, not just a status change) before
marking a finding as closed in the tracking system. For the retest
itself, specifically probe for variants of the original vulnerability
(different exploitation paths against the same underlying flaw), not
just a repeat of the exact original proof-of-concept, to catch fixes that
addressed the symptom rather than the root cause.

## Pitfalls

Don't treat every remediation as requiring a full independent
penetration retest regardless of finding severity -- that may be
disproportionate for low-severity findings; scope the retest requirement
based on severity, with high/critical findings always requiring
independent verification and lower-severity ones potentially satisfied
by a lighter-weight code review confirmation.

## Verify

Confirm the rediscovered vulnerability is now genuinely fixed by
retesting against both the original proof-of-concept and at least one
variant exploitation approach. Going forward, track the percentage of
findings closed with independent verification evidence attached, and
confirm it reaches an acceptable target (ideally near 100% for high/
critical findings).
