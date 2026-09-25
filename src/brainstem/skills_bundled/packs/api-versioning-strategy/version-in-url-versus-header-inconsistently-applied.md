---
name: version-in-url-versus-header-inconsistently-applied
description: An API mixes URL-path versioning and header-based versioning across different endpoints or over time, confusing clients about which mechanism to use and causing version-resolution bugs.
triggers: ["inconsistent api versioning mechanism", "some endpoints use url version others use header", "mixed versioning scheme confusing clients", "version resolution bug mixed mechanisms"]
permissions: ["READ"]
---

## Symptom

Some endpoints of an API expect the version to be specified in the URL
path (`/v2/resource`), while other endpoints (or a later-added set of
endpoints) expect it via a header (`Accept: application/vnd.api+json;
version=2`) -- and clients integrating with multiple endpoints get
confused about which mechanism applies where, sometimes sending the
version the wrong way and silently getting unversioned/default behavior
instead of an error.

## Likely causes

- **The API's versioning scheme was decided early for a subset of
  endpoints, and a later addition to the API (a new service, a new team,
  a different framework default) introduced a different mechanism**
  without reconciling it with the existing convention.
- **No API-wide style guide or platform-level enforcement exists**
  requiring a single, consistent versioning mechanism across all
  endpoints, so individual teams/services made independent, reasonable-
  seeming choices that didn't end up aligned.
- **A framework or gateway default (a specific API gateway's built-in
  versioning support) was adopted for new endpoints without checking it
  matched the existing convention used elsewhere in the API.**
- **The inconsistency was introduced during a migration or refactor**
  (moving some endpoints to a new framework/gateway) without carrying
  forward the original versioning mechanism, and nobody caught the
  discrepancy since each set of endpoints worked correctly in isolation.

## Diagnose

1. Inventory all API endpoints and document which versioning mechanism
   (URL path, header, query parameter) each one actually expects and
   respects.
2. Identify where the inconsistency was introduced by checking when each
   inconsistent set of endpoints was added or last significantly
   changed.
3. Check whether sending the "wrong" mechanism for a given endpoint
   results in an explicit error or silently falls back to default/
   unversioned behavior, since silent fallback is the more dangerous
   failure mode.
4. Survey client integration code/documentation for confusion or
   workarounds already built around this inconsistency.

## Fix

Standardize on a single versioning mechanism across the entire API
going forward, documented as an explicit platform-level convention that
applies to every new endpoint regardless of team or underlying
framework. For existing inconsistent endpoints, either migrate them to
the standard mechanism (with appropriate deprecation notice if it's a
breaking change to existing integrations) or, if migration isn't
immediately feasible, ensure at minimum that sending the wrong mechanism
produces a clear, explicit error rather than silently falling back to
unversioned/default behavior.

## Pitfalls

Don't silently support both mechanisms indefinitely as a "flexible"
compromise -- that permanently bakes in the confusion this skill
addresses rather than resolving it, and makes onboarding new API
consumers harder indefinitely; pick one standard and actively migrate
toward it.

## Verify

Confirm a client sending the now-deprecated/wrong versioning mechanism
for a migrated endpoint receives a clear, actionable error rather than
silent default behavior. Confirm new endpoint documentation and any
automated API contract linting enforces the single standardized
versioning mechanism going forward.
