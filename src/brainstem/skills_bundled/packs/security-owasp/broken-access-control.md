---
name: broken-access-control
description: Diagnose IDOR and missing authorization checks -- a user reaching another user's data or an action above their privilege level by changing an ID or URL, not by breaking authentication.
triggers: ["idor", "insecure direct object reference", "access another user's data", "missing authorization check", "can access other account", "broken access control"]
permissions: ["READ"]
---

## Symptom
An authenticated user can view or modify data/actions that should belong
to someone else, or perform an admin-only action, simply by changing an
ID in a URL/request body or calling an endpoint directly -- authentication
worked correctly (they really are logged in as themselves), but
*authorization* (should this specific user be allowed to touch this
specific resource) was never actually checked.

## Likely causes
1. **An endpoint checks that the user is logged in, but not that they own
   or are permitted to access the specific resource ID in the
   request** -- `GET /orders/{id}` returns any order for any
   authenticated user, not just the requester's own.
2. **Authorization checked in the UI/client only** (a button hidden for
   non-admins) with no corresponding server-side check, so calling the
   API endpoint directly bypasses it entirely.
3. **Role/permission check present on the primary endpoint but missing on
   a secondary one that reaches the same data** -- e.g. the main "edit
   order" endpoint checks ownership, but a bulk-export or webhook-replay
   endpoint touching the same table doesn't.
4. **Sequential/guessable IDs** combined with no ownership check, making
   the vulnerability trivially enumerable (not the root cause itself, but
   what turns a theoretical gap into an easy, high-impact one).
5. **A check that verifies the *type* of relationship but not the
   *specific instance*** -- e.g. confirming "the user has an order" in
   general, rather than "the user owns *this* order ID."

## Diagnose
- For the specific reported endpoint, find the authorization check (or
  its absence): does it verify the resource belongs to (or is otherwise
  permitted for) the authenticated user, not just that *a* user is
  authenticated?
- Enumerate every endpoint that reaches the same underlying resource
  (list, get, update, delete, export, webhook/callback paths) and check
  each independently -- authorization bugs are rarely isolated to one
  endpoint once a pattern like "forgot the ownership check" exists.
- Check whether authorization logic is enforced in one central place
  (a decorator, a middleware, a policy layer) or reimplemented ad hoc per
  endpoint -- ad hoc reimplementation is where these gaps usually live.

## Fix
- Add an explicit ownership/permission check on every endpoint that
  accesses a specific resource by ID: verify the authenticated user is
  permitted for *that specific instance*, not just that they're logged
  in or belong to some general role.
- Centralize authorization logic (a shared policy/permission-check
  function or middleware applied consistently) rather than reimplementing
  the check inline in each handler, so a future new endpoint inherits the
  check by default instead of needing to remember it.
- Audit every endpoint touching the same resource type when one IDOR is
  found, not just the reported one -- treat it as a pattern to eliminate,
  not a single bug to patch.
- Consider non-sequential (UUID) identifiers for sensitive resources as
  defense-in-depth against enumeration, without treating it as a
  substitute for the actual authorization check.

## Pitfalls
- Fixing the check on the primary CRUD endpoints while missing bulk,
  export, admin-impersonation, or webhook-triggered paths that touch the
  same data leaves the vulnerability class present, just harder to find.
- Client-side authorization checks (hiding UI elements) are a UX
  convenience, not a security control -- never treat their presence as
  sufficient; the server must independently enforce the same rule.
- A "the user has *a* record of this type" check that doesn't verify
  *this specific* record's ownership looks like a real check in code
  review but doesn't actually prevent IDOR.

## Verify
As a low-privilege test user, attempt to access/modify another user's
specific resource by ID directly (bypassing the UI, calling the API/URL
directly) and confirm it's rejected with an authorization error --
repeat for every endpoint identified in the diagnose step that touches
the same resource, not just the one originally reported.
