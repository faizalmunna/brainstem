---
name: middleware-order-breaks-auth-protection
description: Diagnose an Express route that executes protected logic before its authentication or authorization middleware actually runs.
triggers: ["auth middleware not blocking requests", "protected route accessible without login", "middleware runs in wrong order", "route handler runs before auth check", "express auth bypass"]
permissions: ["READ"]
---

## Symptom
A route that's supposed to require authentication (or a specific role)
executes its handler logic -- sometimes even sending a response -- for
requests that should have been rejected. It's rarely "auth middleware
does nothing"; more often it's inconsistent: some routes are protected
and others silently aren't, or a route is protected most of the time but
not when reached through a specific path (a router mounted separately, a
static file route, a catch-all).

## Likely causes
1. **The auth middleware is registered after the routes it's meant to
   protect** in `app.use()`/route-definition order -- Express runs
   middleware and route handlers strictly in registration order for a
   matching path, so a route defined (or a router mounted) before
   `app.use(requireAuth)` never passes through it, regardless of where
   `requireAuth` is defined in the file.
2. **The auth middleware is attached only to the router it's declared
   next to, and a route is reachable through a different mount path** --
   e.g. `router.use(requireAuth)` inside `routes/admin.js`, but the same
   handler is also reachable via a route registered directly on the main
   `app` or through a second router that mounts the same handler function
   without going through `admin.js`'s router-level middleware.
3. **The auth middleware doesn't call `next()` on the failure path in a
   way that actually stops the chain** -- e.g. it sends a 401 response
   but doesn't `return` before falling through, so execution continues
   into the next middleware/handler and both a 401 and the protected
   response get written (or the protected logic still executes even
   though a response was already sent).
4. **A wildcard or static-file middleware registered before the auth
   check serves the resource directly**, e.g. `express.static()` mounted
   before `requireAuth` serving files that live under what's assumed to
   be a protected path, bypassing the check entirely for that route.

## Diagnose
- Print the actual middleware/route registration order: grep the app's
  entry point and router files for every `app.use(`, `app.get/post/...`,
  and `router.use(` call, in file order, and reconstruct the order
  Express will actually execute them in for the specific path in
  question -- Express matches in registration order, not by intuition
  about "logical" grouping.
- For the specific failing route, add a temporary `console.log` (or use
  a request-id-tagged debug log) at the top of both the auth middleware
  and the route handler, then hit the route and confirm which one logs
  first -- if the handler logs before (or without) the auth middleware
  logging at all, that confirms the ordering/reachability issue directly
  rather than guessing.
- Check whether the route is reachable through more than one registered
  path (mounted twice, aliased, or matched by a broader wildcard route
  registered earlier) -- test the exact URL a real client would use, not
  just the path as written in the router file, since a leading slash or
  mount-prefix mismatch can route around the middleware you're looking
  at.
- Check every early-return in the auth middleware for a bare
  `res.status(401).json(...)` not followed by `return` -- if `next()` is
  reachable afterward (even indirectly through falling off the end of an
  `if` block), the chain continues.

## Fix
- Register auth middleware for a whole set of routes with `app.use(path,
  requireAuth)` (or `router.use(requireAuth)` at the top of the router
  file, before any route definitions in that file) so it structurally
  cannot be bypassed by a route defined later in the same file --
  ordering becomes a property of the file's top-to-bottom structure
  instead of something to remember per-route.
- Prefer applying auth as router-level middleware over repeating it as a
  per-route argument (`router.get('/x', requireAuth, handler)`) only when
  a router truly needs mixed public/protected routes -- and in that case,
  audit every route in the file for the argument, since it's easy to add
  a new route and forget to include it.
- Ensure every rejecting branch in the auth middleware explicitly
  `return`s after sending a response: `return
  res.status(401).json({...})`, never a bare
  `res.status(401).json({...})` followed by code that can still run.
- If a resource is served by `express.static` or a catch-all route,
  mount the auth check *before* that static/catch-all middleware in
  registration order, or move the protected resource under a path prefix
  that isn't also matched by the public static mount.

## Pitfalls
- Adding `requireAuth` as an argument to every individual route handler
  is easy to get right at first and easy to silently miss on the next
  route someone adds -- prefer router/path-level `use()` so protection is
  structural, not a per-route checklist item.
- Fixing ordering by moving `app.use(requireAuth)` to the very top of the
  whole app can accidentally start requiring auth on routes that must
  stay public (health checks, the login route itself, webhooks) --
  scope the middleware to the specific path prefix it should cover
  instead of applying it globally as a blunt fix.
- A `return` added after `res.status(401).json(...)` fixes the
  double-response bug but doesn't fix broken middleware order elsewhere
  -- verify actual registration order too, since the two causes look
  identical from the client's perspective (protected content leaks) but
  need different fixes.

## Verify
Hit the previously-vulnerable route with no credentials (and, separately,
with valid-but-wrong-role credentials) using the exact URL/mount path a
real client uses, and confirm a 401/403 is returned with no protected
response body -- then repeat with valid credentials and confirm the
route still works, since an overly broad auth mount can fix the leak by
also breaking legitimate access.
