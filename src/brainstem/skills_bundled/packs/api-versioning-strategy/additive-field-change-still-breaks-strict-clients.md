---
name: additive-field-change-still-breaks-strict-clients
description: Adding a new field to an API response, generally considered a safe backward-compatible change, breaks clients that use strict schema validation rejecting any unrecognized field.
triggers: ["adding field broke client", "additive change not actually compatible", "strict schema validation rejected new field", "backward compatible change still broke consumer"]
permissions: ["READ"]
---

## Symptom

An API team adds a new, optional field to a response payload -- a change
that's conventionally considered safe and backward-compatible -- and
one or more client applications immediately start failing, because their
deserialization/validation logic uses strict schema validation that
rejects any field not explicitly defined in the expected schema.

## Likely causes

- **The API provider's compatibility model assumes clients ignore unknown
  fields** (a common and reasonable convention), but at least one client
  was built with strict schema validation (common in some typed
  languages/frameworks, or intentionally for security reasons) that
  rejects anything unexpected rather than ignoring it.
- **No compatibility contract was ever explicitly agreed upon between
  the API provider and consumers** about how unknown fields should be
  handled, so each side made a different reasonable-seeming assumption
  independently.
- **A client library's deserialization was configured for strict mode**
  (rejecting unknown properties) as a general best practice for catching
  typos/bugs during development, without considering the tradeoff against
  tolerating genuinely additive API evolution in production.
- **The specific client wasn't tested against a version of the API
  response that includes fields beyond the currently-known schema**, so
  this brittleness was never discovered until a real additive change
  triggered it.

## Diagnose

1. Confirm the specific new field is the actual trigger by testing the
   failing client against both the old and new response shape in
   isolation.
2. Check the failing client's deserialization/validation configuration
   for whether it's in strict mode (rejecting unknown fields) versus
   permissive mode (ignoring them).
3. Check whether any explicit compatibility contract (documentation, a
   shared schema definition with clear unknown-field-handling semantics)
   exists between the API and its consumers.
4. Identify all other clients and assess whether any others share the
   same strict-validation brittleness, even if not yet triggered by this
   specific change.

## Fix

For the immediate issue, work with the affected client team to switch
their deserialization to permissive mode (ignore unknown fields) for
consuming this API, since this is the industry-standard compatibility
convention and the fix that scales to future additive changes too.
Document an explicit compatibility contract for the API stating that
consumers must tolerate unknown fields, and if any client integration
guide/SDK is provided by the API team, ensure it configures
deserialization permissively by default. Where a client's strict
validation is intentional for a specific legitimate reason (a security-
sensitive use case wanting to catch unexpected fields), that team needs
their own explicit process for reviewing and accepting new fields rather
than treating every one as a break-fix incident.

## Pitfalls

Don't declare "we'll never add fields to avoid breaking strict clients"
as the fix -- that's an overcorrection that permanently limits normal,
healthy API evolution to accommodate one client's non-standard validation
choice; fix the client's validation approach instead, or explicitly
scope the compatibility contract to exclude that pattern going forward.

## Verify

Confirm the affected client, after switching to permissive deserialization,
correctly handles both the old and new response shapes without error.
Add a new field to a test/staging version of the API and confirm all
known client integrations (not just the one that broke) tolerate it
correctly before it's considered a validated, safe additive change
pattern going forward.
