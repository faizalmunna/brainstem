---
name: rest-api-versioning-strategy
description: Choose and apply an API versioning approach that lets you evolve a REST API without breaking existing clients.
triggers: ["api versioning", "how to version rest api", "breaking api change", "deprecate api endpoint", "backwards compatible api change"]
permissions: ["READ"]
---

## Symptom
A needed API change (renaming a field, changing a response shape, removing
a parameter) would break existing clients, and there's no established
pattern in the codebase for shipping it safely -- or there is a versioning
scheme (`/v1/`, `/v2/`) but no clear policy for what triggers a new
version vs. an additive, backward-compatible change.

## Likely causes
This is a design-decision skill more than a bug-diagnosis one, but the
recurring root problem is: **changes get classified as "just a small
tweak" when they're actually breaking**, because there's no explicit
definition of "breaking" the team applies consistently.

## Diagnose
Classify the change first:
1. **Additive, non-breaking**: new optional field, new endpoint, new
   optional query parameter with a sensible default. Existing clients
   ignoring the new field/param continue working unchanged.
2. **Breaking**: renaming/removing a field, changing a field's type or
   meaning, changing required parameters, changing status codes for
   existing cases, changing pagination behavior, tightening validation
   that previously-valid requests would now fail.
3. Ambiguous cases (e.g. adding a new required field) should be treated
   as breaking by default -- if it's unclear, err toward breaking.

## Fix
- For additive changes, ship them without a version bump; document them,
  but don't force clients to migrate.
- For breaking changes, pick one strategy and apply it consistently
  across the API rather than mixing approaches per-endpoint:
  - **URL versioning** (`/v1/orders`, `/v2/orders`) -- simplest to reason
    about and cache, most common for public APIs.
  - **Header-based versioning** (`Accept: application/vnd.api+json;
    version=2`) -- keeps URLs stable, more flexible, but harder for
    clients to discover/debug and harder to test manually.
  - **Additive-only with explicit deprecation** -- never remove/rename,
    only add, and mark old fields deprecated in docs with a sunset date,
    removing them only after a long, communicated window. Works well for
    internal/first-party-client APIs where you control the rollout.
- Whichever strategy is chosen, maintain the previous version's behavior
  fully (not a best-effort shim) until its deprecation window ends, and
  monitor actual traffic to the old version before removing it.

## Pitfalls
- Bumping the version number for the whole API when only one endpoint
  changed forces every client to migrate everything at once, which
  discourages ever shipping a new version -- prefer versioning at the
  resource/endpoint level if the change is localized, or ensure the
  new version is otherwise identical so migration is trivial.
- Silently changing behavior without a version bump because "it's a small
  fix" is how clients break in production without warning -- when in
  doubt, treat it as breaking.
- Removing a deprecated field/version based on "it's been long enough"
  without checking actual traffic can break clients still using it;
  check access logs/metrics for the specific field or version before
  removal, not just the calendar.

## Verify
Before shipping a breaking change, confirm: (1) a previous version/path
still serves the old behavior unchanged, (2) there's a documented,
dated deprecation notice for the old behavior if it will eventually be
removed, and (3) at least one existing client integration test still
passes against the old version's behavior unchanged.
