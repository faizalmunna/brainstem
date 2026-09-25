---
name: internal-and-external-api-versioned-together
description: An API serving both internal services and external customers is versioned as a single artifact, so a change needed only for internal use forces an unnecessary version bump and migration burden on external customers.
triggers: ["internal change forced external api version bump", "coupled internal external api versioning", "external customers affected by internal only change", "single version for internal and external consumers"]
permissions: ["READ"]
---

## Symptom

An API serves both internal microservices and external customer
integrations under the same versioning scheme, and a change needed
purely for internal purposes (an internal service needs a new field, a
different internal consumer needs different behavior) forces a version
bump that then requires external customers to migrate too, even though
nothing relevant to them actually needed to change.

## Likely causes

- **The API was never explicitly designed with separate internal and
  external audiences in mind**, so a single schema/version scheme serves
  both, coupling their release cadences and compatibility requirements
  together even though they have very different actual needs and change
  frequencies.
- **Internal consumers can tolerate faster iteration and less formal
  versioning** (since the team controls both sides and can coordinate
  deploys), while external customers need the stability and formal
  deprecation process a public API requires -- conflating the two forces
  the external-appropriate slower process onto internal changes, or the
  internal-appropriate faster pace onto external customers.
- **No separate internal API surface exists**, so any internal need gets
  bolted onto the existing external-facing API rather than being served
  by a distinct internal-only interface with its own, lighter-weight
  versioning discipline.
- **Splitting the API into separate internal/external surfaces was never
  prioritized** because the original single-API design worked fine until
  the two audiences' needs diverged enough to create real friction.

## Diagnose

1. Review the change that triggered the unnecessary external version
   bump and confirm it genuinely had no relevance to external consumers.
2. Audit how many past version bumps were driven by purely internal needs
   versus genuine external-facing changes, to quantify how often this
   coupling has caused unnecessary external churn.
3. Assess the actual technical overlap between what internal and external
   consumers need from the API -- how much shared surface exists versus
   how much is genuinely audience-specific.
4. Check whether internal consumers have any way to access
   internal-only functionality without going through the externally
   versioned surface.

## Fix

Separate the API into a genuinely distinct internal-facing interface
(with its own, lighter-weight versioning/deployment process appropriate
for a fully-controlled internal audience) and an external-facing
interface (with the more formal versioning/deprecation discipline
external customers require), even if they share underlying
implementation/data. This decouples internal iteration speed from
external stability requirements, so internal-only changes never force
external version bumps again.

## Pitfalls

Don't split into separate internal/external interfaces without a clear
plan for keeping them from drifting into duplicated, inconsistent logic
over time -- share underlying business logic/data access code between
the two interface layers rather than maintaining fully separate
implementations, so the split is about the contract/versioning surface,
not a full duplication of application logic.

## Verify

Confirm the next purely-internal-need change can be made through the
internal interface without requiring any external version bump or
customer-facing migration. Confirm external customers experience the
same or better version stability going forward, measured by version
bump frequency relative to genuinely external-relevant changes only.
