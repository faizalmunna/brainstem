---
name: schema-field-removal-breaks-clients-silently
description: Removing or renaming a GraphQL field in a schema deploy breaks older client builds immediately with no versioned fallback like REST would provide.
triggers: ["graphql breaking change no versioning", "removed field broke old app version", "graphql schema evolution client compatibility", "how to deprecate graphql field safely"]
permissions: ["READ"]
---

## Symptom
A schema change that removes a field, renames it, or changes its type ships to production, and immediately afterward, older client builds (a mobile app version still in app stores, a cached web bundle, a third-party integration) start failing validation on that field with a schema-mismatch error, or -- worse, if the client fetches the query dynamically -- silently receive `null` or an error for that field in an otherwise-successful response, because GraphQL has no built-in equivalent to a REST `/v1/` vs `/v2/` URL path to keep old and new contracts running side by side.

## Likely causes
1. **A field was deleted outright in the same deploy that a new replacement field was added**, on the assumption that "the new field replaces the old one" is obvious, without accounting for the fact that already-deployed clients have the old query baked into their compiled bundle or app binary and cannot be updated instantly.
2. **The team treats the GraphQL schema like an internal implementation detail that can change freely because "the client will just refetch its query,"** which is true for a web app redeployed atomiquely with its backend, but false for any client with an independent release cycle -- native mobile apps, third-party API consumers, or cached SPA bundles.
3. **No schema-change linting or deprecation process is enforced in CI**, so a breaking change (removing a field, changing a field's nullability from nullable to non-null, narrowing an enum, changing a scalar type) ships the same way a purely additive, safe change would, with no automated gate distinguishing the two.
4. **`@deprecated` directive is used for documentation purposes only and never actually checked against real production traffic** before the field is removed, so "deprecated" fields get deleted on a calendar-based assumption rather than evidence that no client is still using them.

## Diagnose
- Run a schema diff tool (`graphql-inspector diff`, Apollo's schema-check, or equivalent) between the previous and proposed schema versions and classify the changes as breaking versus non-breaking (field/type removal, nullability tightening, and enum value removal are breaking; adding a new optional field or enum value is not).
- Check operation-level usage telemetry (Apollo Studio's field usage tracking, or custom resolver-level logging of which fields are actually requested in production traffic) for the field being considered for removal -- if any non-trivial percentage of traffic still selects it, removal will break those callers today, not hypothetically.
- Grep for the field name across all known first-party client codebases (web, mobile, internal services) to catch usages that telemetry might miss (e.g. a rarely-executed code path, or a client not yet reporting telemetry).
- If a field was already removed and clients are failing, check the client-side error: a validation error at query-parse time (schema mismatch) behaves differently from a runtime null/error on a still-parseable query -- this tells you whether the client is validating against a bundled schema copy or trusting the server blindly.

## Fix
Adopt an explicit deprecation lifecycle instead of one-shot removal, since GraphQL versioning happens at the field level, not the endpoint level:
- Mark a field `@deprecated(reason: "Use newField instead, will be removed after <date/version>")` and keep it fully functional (delegating internally to new logic if needed) for a defined grace period, rather than removing it the moment a replacement exists.
- Use field-usage telemetry to gate actual removal on evidence -- only remove a deprecated field once production traffic shows zero (or a deliberately accepted residual) usage over a meaningful window, not on a fixed calendar date alone.
- For changes that are unavoidably breaking for specific known consumers (e.g. a documented public API with external partners), communicate a deprecation timeline out-of-band (changelog, email, API status page) the same way a REST API version sunset would be communicated, since GraphQL's single-schema model makes silent breakage easier to ship by accident.
- Prefer additive evolution where possible: add a new field alongside the old one rather than changing an existing field's type or nullability in place, since narrowing an existing field's contract (nullable to non-null, widening to narrowing enum) breaks clients that never even asked for the new behavior.

## Pitfalls
Treating `@deprecated` as sufficient documentation and then removing the field on schedule regardless of usage data defeats the entire purpose of the directive -- deprecation without an enforced usage-based gate before removal is functionally identical to just breaking clients on a delay, and teams often discover this only after the removal deploy when support tickets start.

## Verify
Run the schema-diff/breaking-change check in CI against the proposed schema and confirm it flags the change's classification correctly (breaking vs. safe), and before removing any `@deprecated` field, pull its field-usage telemetry for a recent window (e.g. 30 days) and confirm it shows zero production queries selecting that field.
