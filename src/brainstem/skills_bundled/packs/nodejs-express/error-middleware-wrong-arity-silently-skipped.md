---
name: error-middleware-wrong-arity-silently-skipped
description: Diagnose an Express error-handling middleware that never runs because its function signature doesn't have exactly four parameters.
triggers: ["error handler never fires in express", "next(err) has no effect", "custom error middleware ignored", "express default error handler stack trace in production", "centralized error handling not working"]
permissions: ["READ"]
---

## Symptom
A dedicated error-handling middleware function is registered with
`app.use(errorHandler)`, and the app definitely calls `next(err)` (or an
error is thrown) somewhere upstream, but `errorHandler` never executes --
instead, Express's built-in default error handler takes over, sending a
generic response (or, in development mode, a raw stack trace to the
client) as if the custom handler didn't exist at all. Logging statements
placed at the top of the custom handler simply never print.

## Likely causes
1. **The error-handling middleware function does not have exactly four
   parameters** -- Express distinguishes error-handling middleware from
   regular middleware purely by counting the function's declared
   parameters (`(err, req, res, next)`, arity 4); a function like `(err,
   req, res) => {...}` (arity 3, e.g. because `next` was removed since it
   looked unused) or one that destructures/omits a parameter is treated
   by Express as *regular* middleware, and regular middleware is never
   invoked for error handling regardless of its name or intent.
2. **The error-handling middleware is registered before some of the
   routes/middleware it's meant to cover**, not after -- Express requires
   error handlers to be registered *last*, after all other `app.use()`
   and route definitions, since it only routes an error to error-handling
   middleware registered later in the stack than where the error
   occurred.
3. **An error occurs inside a synchronous piece of code that isn't
   wrapped correctly, or inside an async handler on Express 4 with no
   `next(err)` forwarding** (see `async-handler-error-not-caught-by-
   express`) -- in that case no error middleware runs at all, four-
   argument or not, because the error never reaches Express's error-
   handling path in the first place; this is a different root cause
   producing a similar-looking "my error handler never runs" report.
4. **Multiple error-handling middleware functions are registered, and an
   earlier one sends a response without calling `next(err)` to pass
   control to the next one**, so a later, more specific error handler
   never gets a chance to run even though it's correctly shaped and
   positioned.

## Diagnose
- Read the exact signature of the error-handling middleware function
  character by character -- count the parameters. This is a purely
  mechanical check and the single most common cause: `(err, req, res,
  next)` must be exactly four, in that order; a linter won't catch this
  since a 3-argument function is syntactically valid, it's just treated
  differently by Express at runtime.
- Confirm the error actually reaches Express's dispatch mechanism at all:
  add a temporary generic error middleware
  (`app.use((err, req, res, next) => { console.log('ERROR REACHED
  HANDLER', err); res.status(500).end(); })`) as the very last `app.use()`
  call, and check whether *it* fires -- if it doesn't either, the problem
  is upstream (the error isn't reaching any error middleware, e.g. an
  uncaught async rejection), not the specific custom handler's shape or
  position.
- Check registration order explicitly: print out (or read top-to-bottom
  in the entry file) every `app.use()`/route registration and confirm the
  custom error handler is the last thing registered, after every route
  and other middleware.
- If multiple error handlers exist, check each one for whether it calls
  `next(err)` to pass through to the next, versus unconditionally ending
  the response -- an earlier handler swallowing the response prevents a
  later, more specific one from ever running.

## Fix
- Ensure the error-handling middleware's function signature has exactly
  four parameters, in the exact order `(err, req, res, next)`, even if
  `next` is never called inside the body -- if a linter flags `next` as
  unused, disable that specific warning for this function rather than
  removing the parameter, since removing it changes Express's runtime
  behavior, not just a style concern.
- Register the error-handling middleware after every other `app.use()`
  call and every route definition, as the last thing added to the app
  (or the last thing added to a given router, if it's meant to be
  scoped to that router only).
- When chaining multiple error handlers (e.g. a specific one for
  validation errors, a generic fallback last), have each one call
  `next(err)` to pass the error along unless it's confident it's the
  right handler for that error type and intends to end the response
  itself.
- Combine this with the fix for `async-handler-error-not-caught-by-
  express` where relevant -- a correctly-shaped, correctly-positioned
  error handler still won't run if nothing ever calls `next(err)` for
  errors originating in async route handlers on Express 4.

## Pitfalls
- Renaming the four-argument handler's parameters to something other
  than the conventional `err, req, res, next` (Express doesn't care about
  names, only position and count) is fine and sometimes done to avoid
  shadowing, but removing a parameter entirely to satisfy a "no unused
  vars" lint rule silently breaks the handler -- prefix the unused
  parameter with an underscore or add a targeted lint-disable comment
  instead of deleting it.
- Registering the error handler last but still before an async route
  defined even later in a different file that's mounted after the main
  error handler (e.g. via `app.use('/late', lateRouter)` after
  `app.use(errorHandler)`) reintroduces the ordering problem for that
  router specifically -- error-handling middleware must come after
  *everything* it's meant to cover, including routers mounted later.
- Assuming the built-in default Express error handler is "doing nothing"
  when a custom one is misconfigured -- it's actually running and
  producing a response (often with a stack trace visible in non-
  production `NODE_ENV`), which can look like "the request just failed
  weirdly" rather than "my error handler was skipped" if the default
  response isn't recognized for what it is.

## Verify
Trigger a deliberate error on a route covered by the custom handler and
confirm, via a log statement inside it, that the custom handler executes
and produces its intended response format -- not Express's default error
page/stack-trace response -- and repeat for at least one route defined
after the error handler's registration point to confirm no ordering gap
remains.
