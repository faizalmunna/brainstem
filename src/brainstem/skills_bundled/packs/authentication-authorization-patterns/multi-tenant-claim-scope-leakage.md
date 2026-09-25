---
name: multi-tenant-claim-scope-leakage
description: An authorization check passes because a token's role or permission claim is valid in general but was never scoped to the specific tenant being accessed.
triggers: ["user can access another tenant's data with valid token", "multi tenant token scope bug", "role claim not tenant specific", "cross tenant data leak with valid jwt", "org id not checked against token"]
permissions: ["READ"]
---

## Symptom
In a multi-tenant (multi-organization/multi-workspace) system, a user with a legitimately issued, correctly signed token for Tenant A is able to access or act on data belonging to Tenant B -- not by forging anything, but because the token's claims (role, permissions) are checked without also confirming they apply to *this* tenant. Often surfaces when a user is a member of multiple tenants (e.g. an admin of one workspace, a regular member of another) and a request meant for one tenant context is authorized using a role claim that was actually granted for a different one.

## Likely causes
1. **The token carries a role claim without a tenant identifier**, e.g. `{"role": "admin"}` instead of `{"tenant_id": "acme", "role": "admin"}` -- so once decoded, "admin" reads as globally true rather than "admin of Acme specifically," and any endpoint checking `role == "admin"` grants access regardless of which tenant's resource is being requested.
2. **The tenant ID is taken from the request (a URL param, header, or request body) rather than derived from the token/session**, so the authorization check verifies the user has *some* valid role, then trusts the client-supplied tenant ID to decide *which* tenant's data to return -- letting a user simply change the tenant ID in the request while keeping their own valid token.
3. **A token is issued per-login covering all of a user's tenant memberships at once** (an array of `{tenant_id, role}` pairs) but the authorization check only verifies "does this array contain a role of at least X" without also checking that the *specific* entry matches the tenant being accessed.
4. **Caching or session state leaks the "current tenant" across requests** -- a user switches tenant context in the UI, but a cached authorization decision or a stale claim from a previous request is reused for a request that should be scoped to the new tenant.
5. **Superadmin/staff tooling reuses the same token/role-check path as regular tenant access**, and a broad "is staff" claim satisfies a check that should additionally confirm explicit, audited cross-tenant access was granted for this specific case.

## Diagnose
- Decode a token for a user who belongs to two or more tenants and inspect exactly what tenant-scoping information it carries -- is `tenant_id` bound to each role/permission claim, or is there a single flat role claim with tenant selection happening elsewhere?
- For a specific authorization check in code, trace where the tenant ID being checked against actually comes from: the verified token/session, or a request parameter -- if it's the latter, check whether that parameter is cross-validated against the user's actual memberships.
- As a test user belonging to Tenant A only, attempt to access a Tenant B resource by changing the tenant identifier in the URL/header/body while keeping your own valid token, for each endpoint category (read, write, admin actions).
- If tokens carry a list of tenant memberships, check the authorization middleware for whether it does `any(role >= required for membership in memberships)` (wrong -- ignores which tenant is targeted) versus finding the specific membership entry matching the requested tenant first.

## Fix
Bind every role/permission claim to the tenant it applies to, either by issuing tenant-scoped tokens (a token obtained for/after selecting a specific tenant context, carrying that single `tenant_id` plus the role within it) or, for tokens covering multiple memberships, requiring every authorization check to first look up the membership entry matching the *target* tenant of the specific request and only then check its role/permission -- never checking "does the user have this role anywhere" independent of which tenant's resource is being touched. Derive the tenant being acted on primarily from trusted context (the resource being fetched, e.g. `order.tenant_id` loaded from the DB) and treat any client-supplied tenant identifier as merely a hint to be cross-checked against that trusted value, never as the sole input to the authorization decision.

## Pitfalls
Adding a tenant_id check that compares the client-supplied tenant ID against the token's tenant claim, but still trusting the client-supplied ID to decide *which resource* to fetch in the first place, can still leak data if the fetch itself isn't independently scoped by tenant (e.g. `SELECT * FROM orders WHERE id = ?` without also constraining `AND tenant_id = ?` from the trusted source). Also, "fixing" this by adding a `tenant_id` column that's set but never included in the actual `WHERE` clause of queries is a common incomplete migration -- the schema looks right but the queries weren't updated.

## Verify
As a test user who is a genuine member of Tenant A (with a real, validly issued role there) but not a member of Tenant B, attempt every category of action (read, write, admin, delete) against Tenant B's resources using your own valid token, varying any client-suppliable tenant identifier to point at Tenant B, and confirm each is rejected -- then confirm the same actions succeed normally when correctly scoped to Tenant A.
