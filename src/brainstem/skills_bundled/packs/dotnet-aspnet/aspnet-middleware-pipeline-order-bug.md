---
name: aspnet-middleware-pipeline-order-bug
description: Diagnose ASP.NET Core requests that bypass authentication or authorization because middleware was registered in the wrong pipeline order.
triggers: ["authorization not enforced aspnet core", "endpoint runs before auth middleware", "app.userouting order matters", "401 not returned but should be", "middleware pipeline order wrong"]
permissions: ["READ"]
---

## Symptom
An endpoint that should require authentication or a specific role is
reachable anonymously or by any authenticated user regardless of role,
even though `[Authorize]` (or an equivalent policy) is present on the
action -- or a custom middleware that should see every request (logging,
exception handling, CORS) either never runs or runs after the response
has already started. No exception is thrown; the app just behaves as if
the security or cross-cutting middleware isn't there.

## Likely causes
1. **`UseAuthorization()` called before `UseAuthentication()`** -- ASP.NET
   Core's authorization middleware needs `HttpContext.User` already
   populated by authentication to evaluate policies; if authorization
   runs first, it either fails closed unexpectedly or, depending on
   policy configuration, doesn't get the identity it needs to make the
   right decision.
2. **`UseAuthentication()`/`UseAuthorization()` placed after
   `UseEndpoints()`/before endpoint routing is set up (`UseRouting()`)**
   -- both auth middleware must sit between `UseRouting()` and the
   terminal endpoint execution; if routing hasn't run yet, there's no
   endpoint metadata (like `[Authorize]` attributes) for the authorization
   middleware to evaluate yet, so it silently no-ops.
3. **A custom middleware calls `await _next(context)` conditionally or
   not at all**, short-circuiting the pipeline before later middleware
   (including auth) runs for some requests -- easy to introduce when
   someone adds an early-return branch (e.g. for health-check paths) that
   accidentally also matches real routes.
4. **Exception-handling or response-modifying middleware
   (`UseExceptionHandler`, custom logging/response-wrapping middleware)
   registered after the components whose exceptions or responses it's
   meant to catch/modify** -- middleware only affects what happens
   "below" it in the pipeline for the request phase, and "above" it in
   reverse order for the response phase, so ordering mistakes here
   silently produce unhandled exceptions or unwrapped responses instead
   of the intended cross-cutting behavior.

## Diagnose
- Read `Program.cs` (or `Startup.Configure`) top to bottom and list the
  exact middleware order; compare it against the documented required
  order: exception/error handling first, then HTTPS redirection, static
  files, `UseRouting()`, CORS, `UseAuthentication()`,
  `UseAuthorization()`, custom middleware needing identity, then
  `UseEndpoints()`/`MapControllers()`/minimal API route mappings.
- Add a temporary logging middleware at the very start and immediately
  before/after each suspect middleware that writes
  `context.User.Identity.IsAuthenticated` and the matched endpoint name
  -- if `IsAuthenticated` is false at a point where it should already be
  true, the ordering (or a short-circuit before that point) is confirmed
  as the cause.
- Send an unauthenticated request to the protected endpoint with a tool
  that shows the full response (curl/Postman) and confirm whether it
  returns 200 (bug) instead of the expected 401/302-to-login -- then
  check whether the auth middleware ran at all for that request via the
  logging above.
- For a custom middleware suspected of short-circuiting, grep it for
  every code path and confirm each one either calls `await _next(context)`
  or intentionally terminates the response (e.g. a health check) --
  anything in between is a bug.

## Fix
- Reorder the pipeline to match the framework-required sequence:
  `UseExceptionHandler`/`UseHsts` -> `UseHttpsRedirection` ->
  `UseStaticFiles` -> `UseRouting()` -> `UseCors()` ->
  `UseAuthentication()` -> `UseAuthorization()` -> any custom middleware
  that depends on the authenticated user -> `MapControllers()`/endpoint
  mapping. Treat this order as a contract, not a suggestion -- each stage
  depends on state set up by the one before it.
- For a custom short-circuiting middleware, make every non-terminal
  branch explicitly call `await _next(context)`, and add a code comment
  at each intentional early-return explaining why that path is meant to
  bypass the rest of the pipeline (e.g. a health-check endpoint that must
  stay anonymous), so the next editor doesn't "fix" it into a bug or
  reintroduce this one elsewhere.
- When multiple teams add middleware over time, centralize the
  registration in one reviewed extension method (e.g.
  `app.UseAppMiddlewarePipeline()`) with the order commented, rather than
  letting `Program.cs` accumulate `app.Use...()` calls in whatever order
  people appended them.

## Pitfalls
- Moving `UseAuthorization()` earlier to "fix" one broken endpoint can
  break a different endpoint that relied on a middleware between routing
  and authorization (e.g. one that sets a claim used by a policy) --
  re-verify every protected route after any pipeline reorder, not just
  the one that prompted the change.
- Adding `[Authorize]` to more controllers without checking the pipeline
  order treats the symptom (unauthorized access) without fixing the root
  cause -- if the order is wrong, newly-attributed endpoints will have
  the identical bug.

## Verify
After reordering, send an unauthenticated request to the previously
vulnerable endpoint and confirm it now returns 401 (or redirects to
login), then send a request as an authenticated user lacking the
required role/policy and confirm it returns 403 -- both outcomes must be
correct, since fixing only the anonymous case can still leave role-based
authorization unenforced if a different ordering mistake is present.
