---
name: uniform-scrutiny-regardless-of-risk-area
description: A pull request touching a critical, high-risk area of the codebase (authentication, payments, data deletion) receives the same review scrutiny as a low-risk change, because there's no differentiated review process based on risk.
triggers: ["high risk change reviewed like any other", "auth code got normal review not extra scrutiny", "payment code bug from insufficient review", "no risk based review process"]
permissions: ["READ"]
---

## Symptom

A bug or security issue is discovered in a high-risk area of the
codebase (authentication, payment processing, data deletion,
permissions/access control) shortly after a change merged there -- and
investigation shows the PR received the same review process (one
reviewer, standard turnaround time, no special checklist) as any
ordinary, low-risk change, despite the area's inherently higher blast
radius for mistakes.

## Likely causes

- **No formal or informal designation exists for which parts of the
  codebase are high-risk**, so there's no trigger that would prompt
  extra scrutiny -- every PR is treated identically by default
  regardless of what it touches.
- **The team relies on individual reviewer judgment to recognize a
  change as high-risk and apply extra care**, which works inconsistently
  since not every reviewer has the context to recognize a given area's
  risk level, especially newer team members.
- **Extra review requirements for high-risk areas were discussed at some
  point but never actually implemented as an enforced process** (a
  required second reviewer, a mandatory security-focused checklist), so
  the intention existed without a mechanism to guarantee it happens.
- **Time pressure treats all PRs as equally urgent to merge quickly**,
  so even a change to a recognized high-risk area doesn't get the
  additional review time it would need, because the team's velocity
  norms don't differentiate.

## Diagnose

1. Confirm which specific codebase areas are genuinely high-risk (based
   on past incident history, business criticality, blast radius of a
   mistake) to establish a concrete, evidence-based list rather than a
   vague sense.
2. Check whether the specific PR that caused the incident actually
   touched code that would be on that high-risk list.
3. Review the actual review process that PR went through (number of
   reviewers, their familiarity with the area, turnaround time) against
   what a differentiated process would have required.
4. Check whether any tooling (CODEOWNERS files, path-based required
   reviewers) exists that could enforce differentiated review but isn't
   configured for the relevant paths.

## Fix

Explicitly designate high-risk code areas (informed by real incident
history and business criticality) and enforce differentiated review
requirements for changes touching them -- a required second reviewer
with specific domain expertise, a dedicated checklist covering the
area's known risk patterns (for auth: session handling, permission
checks; for payments: idempotency, amount validation), or a mandatory
minimum review time before merge is allowed. Use tooling (CODEOWNERS,
path-based branch protection rules) to enforce this automatically rather
than relying on reviewers remembering which areas need extra care.

## Pitfalls

Don't apply heavyweight extra-scrutiny requirements to an overly broad
definition of "high-risk" -- if too much of the codebase is tagged as
requiring extra process, it becomes normalized friction that slows
everything down without meaningfully improving scrutiny where it matters
most; keep the high-risk designation genuinely scoped to the highest-
blast-radius areas.

## Verify

Confirm the tooling-enforced differentiated review requirement actually
triggers correctly for a test change touching a designated high-risk
path (a required reviewer is added automatically, or merge is blocked
without the checklist being completed). Track incident rate in
designated high-risk areas over subsequent months and confirm it trends
down relative to the historical baseline.
