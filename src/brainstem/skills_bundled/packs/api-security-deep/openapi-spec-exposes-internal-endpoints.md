---
name: openapi-spec-exposes-internal-endpoints
description: An auto-published OpenAPI or Swagger document publicly exposes internal or admin-only endpoints that were never meant to be discoverable by outside users.
triggers: ["Swagger docs expose admin routes publicly", "OpenAPI spec leaking internal endpoints", "auto generated API docs show endpoints that should be hidden", "public API documentation reveals unreleased features"]
permissions: ["READ"]
---

## Symptom
The API's `/swagger.json`, `/openapi.yaml`, or an interactive docs UI (Swagger UI, Redoc) is reachable without authentication, and browsing it reveals endpoints that were never intended for public/external consumption: `/internal/admin/users`, `/debug/reset-cache`, `/v2/experimental/*`, or endpoints for a feature that hasn't publicly launched yet -- handing anyone who finds the docs a complete map of attack surface, including things access control alone was supposed to keep obscure.

## Likely causes
1. **The OpenAPI spec is auto-generated from the entire route table/codebase** (common with frameworks that introspect all registered routes and decorators to build the spec), with no separation between routes meant for public API consumers and internal/admin routes that happen to live in the same codebase and router.
2. **The docs endpoint itself has no access control**, having been left in its framework-default configuration (many web frameworks enable interactive API docs by default in development and the setting is never revisited for production) -- the assumption was that if the underlying endpoints are protected, the *documentation* of them is harmless, which ignores that documentation itself is reconnaissance value.
3. **Internal and public APIs share one router/application instance** rather than being split into separate services or at least separate spec-generation scopes, so there's no natural boundary at which to exclude internal routes from the generated spec.
4. **A tagging/visibility convention exists in principle** (e.g. routes tagged `internal` should be excluded) **but isn't enforced automatically** -- it depends on every developer remembering to tag new internal routes correctly, and it silently fails open (untagged = included) rather than fail closed (untagged = excluded pending review).

## Diagnose
- Fetch the live OpenAPI/Swagger document from the production docs endpoint (unauthenticated, as an external user would) and review every listed path for anything that looks internal-only, admin-only, debug/diagnostic, or unreleased -- don't rely on memory of what should be there.
- Check whether the docs UI or raw spec endpoint itself requires authentication -- if the interactive Swagger UI is reachable at a predictable path with no login, that's the direct gap regardless of what the spec contains.
- Check the spec-generation configuration/code for how it decides which routes to include -- is it introspecting the full route table by default (include-all) or building from an explicit list/tag (include-only-marked)?
- Search the router/codebase for internal or admin route definitions and confirm whether they live in the same application instance and spec-generation scope as public-facing routes, or a genuinely separate one.

## Fix
Make internal/admin route exclusion structural, not convention-based, and gate the docs themselves:
- Require authentication (and ideally IP allowlisting or VPN-only access) on the docs UI and raw spec endpoints in any environment reachable from the public internet -- documentation of an attack surface is itself sensitive, independent of whether the underlying endpoints are separately protected.
- Generate separate OpenAPI specs for separate audiences: an explicit include-list or a router-level split (internal routes registered on a distinct router/app instance that spec-generation never touches) rather than one auto-introspected spec with exclusions bolted on.
- If a tagging convention is used to mark internal routes, make it fail closed: untagged or ambiguously-tagged routes should be excluded from the public spec by default, requiring an explicit "publish externally" opt-in rather than an opt-out.
- Add a CI check that diffs the publicly-generated spec against an approved baseline and fails the build if a new path appears that wasn't explicitly reviewed for public exposure.

## Pitfalls
Don't treat "the internal endpoints still require their own authentication" as sufficient justification for leaving them listed in a public spec -- a public spec turns unauthenticated recon (probing for endpoints) into a solved problem for an attacker, and often reveals parameter names, internal field names, or feature flags that make subsequent attacks (including on the auth layer itself) meaningfully easier.

## Verify
Fetch the production OpenAPI spec anonymously after the fix and confirm it contains only the intended public route set (diff against the approved baseline), and confirm a direct unauthenticated request to the docs UI/spec path now returns 401/403 rather than the document.
