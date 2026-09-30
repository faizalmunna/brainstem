---
name: breaking-change-shipped-without-version-bump
description: An API change that breaks existing client behavior is deployed without incrementing the API version, silently breaking every client that depended on the old behavior.
triggers: ["breaking change no version bump", "api change broke clients silently", "backward incompatible change shipped as patch", "clients broke after api deploy"]
permissions: ["READ"]
---

## Symptom

An API change is deployed, and shortly afterward, one or more client
applications start failing or behaving incorrectly -- investigation
reveals the deployed change altered response structure, field
semantics, or required parameters in a way that breaks the existing
contract, but the API version wasn't incremented, so clients had no
signal that anything incompatible had changed.

## Likely causes

- **No clear definition exists of what constitutes a "breaking change"**
  for this specific API, so a change that removes a field, renames one,
  or changes a value's type/meaning was judged (incorrectly) as safe by
  whoever made it, without a shared understanding of compatibility
  rules.
- **The change was intended as a bug fix** (correcting what seemed like
  wrong behavior) without considering that clients may have already
  built around the "wrong" behavior, making the fix itself a breaking
  change from the client's perspective regardless of original intent.
- **No automated compatibility check exists in the API's release
  process** that would flag a structural or semantic change against the
  previous version's contract before deployment.
- **Versioning discipline was treated as optional/informal**, with
  version bumps happening only when someone remembered to do it manually,
  rather than being enforced as part of the deployment process itself.

## Diagnose

1. Diff the API's actual request/response contract (via API schema,
   OpenAPI spec, or direct comparison of real requests/responses) between
   the version before and after the change to identify exactly what
   changed structurally or semantically.
2. Classify the specific change against a clear compatibility
   definition (removed/renamed field, changed type, changed required-
   ness, changed semantic meaning of an existing field) to confirm it's
   genuinely breaking, not just perceived as breaking.
3. Identify which client applications/consumers were actually affected
   and how, to understand real-world impact.
4. Check whether any automated schema/contract diffing exists in the
   release pipeline, and if not, why this specific change wasn't manually
   caught before deployment.

## Fix

Establish (or reinforce) an explicit, documented definition of
compatibility rules for the API (what's safe: adding optional fields;
what's breaking: removing/renaming fields, changing types, changing
required-ness or semantics). Roll back or provide a compatibility shim
for the specific breaking change that shipped, giving affected clients
time to migrate. Add automated schema/contract diffing to the release
pipeline that flags any breaking change against the previous version
before deployment, requiring an explicit version bump (and the
corresponding versioning/deprecation process) for any change classified
as breaking.

## Pitfalls

Don't treat "it was technically a bug fix" as an exemption from
versioning discipline -- from the client's perspective, a change that
breaks their working integration is breaking regardless of whether the
original behavior was a bug; if backward compatibility matters, bug
fixes that change externally-visible behavior need the same versioning
treatment as any other breaking change.

## Verify

Confirm the automated schema-diffing check, once added, correctly flags
a deliberately introduced breaking change in a test scenario before it
reaches deployment. For the specific incident, confirm affected clients
are either working again (via rollback/shim) or have a clear, communicated
migration path with adequate notice.
