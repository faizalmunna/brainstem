---
name: inconsistent-authorization-enforcement-across-endpoints
description: A newly added endpoint ships with no role or permission check because authorization is enforced ad hoc per-handler instead of through one shared mechanism.
triggers: ["forgot to add auth check on new endpoint", "role check missing on new route", "authorization inconsistent across codebase", "new api route has no permission check", "admin endpoint accidentally public"]
permissions: ["READ"]
---

## Symptom
An audit or incident reveals that some endpoint -- often a recently added one -- has no role/permission check at all, even though equivalent endpoints elsewhere in the same API correctly enforce one. This isn't a single missing ownership check on one resource (that's IDOR/broken access control on a specific object); it's a structural gap where an entire class of protection (e.g. "must be an admin," "must have the `billing:write` permission") is simply absent because the codebase has no single place that guarantees it's applied, and each handler was individually responsible for remembering to add it.

## Likely causes
1. **Authorization is implemented inline, per-handler**, copy-pasted from similar endpoints -- when a new endpoint is written from scratch (or copied from a handler that itself lacked the check), there's nothing that fails loudly if the check is omitted; the endpoint just works, unprotected.
2. **A central mechanism exists (middleware, decorator, route-level config) but is opt-in rather than opt-out** -- routes are unprotected by default and must explicitly declare a required role, so a forgotten declaration silently means "public," rather than the reverse (protected by default, explicitly opted out for genuinely public routes).
3. **Multiple authorization mechanisms coexist inconsistently** -- older routes use a decorator, newer ones use a different middleware layer, a GraphQL resolver layer has its own separate check entirely -- so "authorization is enforced" is true of the codebase in aggregate but not verifiable by looking at any one place.
4. **No automated test or lint rule asserts every route has an authorization requirement**, so the gap is only ever caught by manual review or, worse, by an incident -- there's no CI signal that would have caught the new endpoint shipping unprotected.
5. **Framework routing allows a route to be registered without going through the app's standard router setup** (a quick debug/internal route, a file-based routing convention with an unusual file placement) that bypasses wherever the authorization middleware is normally attached.

## Diagnose
- Pick a sample of endpoints across the codebase's history (oldest and newest) and check, for each, exactly how its authorization requirement is declared -- is it a consistent, greppable pattern (a decorator name, a middleware config entry) or does it vary by file/age?
- Search for any route registration that doesn't go through the app's central router/middleware stack (a standalone debug blueprint, a manually mounted sub-app, a framework escape hatch) as a likely place for the pattern to be silently skipped.
- Check whether authorization is default-deny (routes require explicit configuration to be reachable, and are protected unless marked public) or default-allow (routes are open unless explicitly protected) -- default-allow is the higher-risk shape, since a forgotten declaration fails open.
- If there's a test suite, check whether any test asserts that unauthenticated/under-privileged requests are rejected for *every* route, or only for the specific routes someone thought to write a test for.

## Fix
Move authorization enforcement to a single, centralized layer that's default-deny: register it at the framework's router/middleware level so every new route must explicitly declare what it needs (a required role, permission, or an explicit "this is intentionally public" marker) to be reachable at all, rather than defaulting to open. Where the framework doesn't support this natively, add a CI check (a test that enumerates all registered routes and asserts each has a recognized authorization declaration, failing the build if a new route has none) so a missing check is caught before merge, not after an incident. Consolidate competing authorization mechanisms (old decorator + new middleware + separate GraphQL checks) into one, even if it's a larger migration, since "authorization is enforced somewhere" isn't verifiable or auditable when it's split across inconsistent systems.

## Pitfalls
A "default public unless marked" model feels lower-friction during development (nothing blocks a new route while it's being built) but is exactly the shape that produces this bug in production -- prefer the friction of default-deny over the risk of default-allow, even though it means explicitly marking genuinely public routes. Also, a route-enumeration test that only checks routes are *decorated* with something, without checking the decorator actually maps to a real, restrictive permission (versus e.g. an empty/no-op permission set applied by copy-paste), can pass while still leaving the route effectively open.

## Verify
Add (or run, if it exists) an automated test that enumerates every registered route in the application and asserts each one resolves to an explicit authorization requirement or an explicit, reviewed "intentionally public" allowlist entry; confirm it fails when a new route is added with neither, and confirm it currently passes (or lists every existing gap) against the present codebase.
