---
name: scope-creep-during-live-engagement
description: A penetration test drifts into testing systems or techniques outside the agreed scope during the engagement, creating legal and operational risk for both the testers and the client.
triggers: ["pentest scope creep", "tester went beyond agreed scope", "penetration test touched out of scope system", "engagement scope not respected during testing"]
permissions: ["READ"]
---

## Symptom

During or after a penetration testing engagement, it's discovered that
testing activity touched systems, techniques, or a testing window
outside what was explicitly agreed in the engagement's scope document --
creating legal exposure (unauthorized access to something not
covered by the authorization), operational risk (an unintended outage
or side effect on an out-of-scope system), or simply invalidating the
report's findings against what the client actually authorized.

## Likely causes

- **A discovered vulnerability or lead naturally pointed toward a
  system outside the defined scope** (a shared authentication system, a
  third-party integration), and the tester followed it without pausing
  to get explicit authorization to extend scope, treating "it's clearly
  related" as sufficient justification on its own.
- **The scope document itself was ambiguous** about boundaries (an IP
  range that turns out to include more than intended, a "web
  application" scope that doesn't clearly exclude a linked third-party
  service), leaving room for good-faith disagreement about what was
  actually authorized.
- **Time pressure to find findings within a fixed engagement window**
  pushed the tester toward opportunistic scope expansion when the
  originally scoped systems didn't yield findings quickly enough.
- **No real-time communication channel or checkpoint exists during the
  engagement** for the tester to quickly request scope clarification/
  expansion when a legitimate question arises, so ambiguous situations
  get resolved unilaterally rather than confirmed with the client first.

## Diagnose

1. Compare the engagement's signed scope document precisely against what
   was actually tested (systems touched, techniques used, time windows),
   identifying the exact discrepancy.
2. Review any communication logs from during the engagement for whether
   the tester attempted to raise the scope question and didn't get a
   timely response, versus never raising it at all.
3. Assess the actual impact of the scope excursion -- was it passive
   reconnaissance with no real risk, or active exploitation with
   potential for real harm to the out-of-scope system.
4. Review the scope document's specific language for genuine ambiguity
   versus a clear boundary that was simply crossed.

## Fix

Establish a real-time communication channel (a point of contact
available during the entire engagement window) so scope questions can be
resolved quickly rather than left to unilateral judgment calls under
time pressure. Write scope documents with explicit, unambiguous
boundaries (exact IP ranges/domains, explicit inclusion/exclusion of
third-party/shared systems) reviewed by both parties before the
engagement starts, specifically anticipating common ambiguous cases
(shared auth systems, third-party integrations) rather than leaving them
implicit. Where a legitimate lead points outside scope, the correct
action is always to pause, document the lead, and request explicit
authorization to extend scope -- never to proceed and seek forgiveness
afterward.

## Pitfalls

Don't treat "the finding was valuable" as retroactive justification for
an out-of-scope excursion -- the value of a finding doesn't change
whether unauthorized access to a system occurred, and treating value as
justification normalizes exactly the behavior that creates real legal
risk for both the tester and the client.

## Verify

Review the final report specifically for any finding that falls outside
the signed scope and either obtain explicit retroactive authorization
documenting it, or exclude it from the report entirely. For future
engagements, confirm the scope document explicitly addresses the
specific category of ambiguity that caused this incident.
