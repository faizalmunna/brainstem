---
name: async-handler-error-not-caught-by-express
description: Diagnose an async Express route whose thrown error or rejected promise never reaches the error-handling middleware and instead hangs the request or crashes the process.
triggers: ["express error handler never called", "async route hangs on error", "request times out instead of 500", "express 4 async errors not caught", "next(err) never triggered"]
permissions: ["READ"]
---

## Symptom
An `async` Express route handler throws or awaits a rejected promise, and
instead of the app's error-handling middleware producing a 500 response,
one of two things happens: the request hangs until the client times out
(no response is ever sent), or the process crashes/logs an unhandled
rejection (see `unhandled-promise-rejection-crashes-process` for that
failure mode specifically). This is distinct from "the error handler runs
but formats the response wrong" -- here the error handler doesn't run at
all.

## Likely causes
1. **Running Express 4.x (or earlier) with a plain `async` route
   handler**, e.g. `app.get('/x', async (req, res) => { throw new
   Error('boom') })` -- Express 4's routing layer was written before
   `async`/`await` existed and does not await handler return values or
   catch the rejection an `async` function's thrown error becomes; the
   error simply has no `next(err)` call anywhere and the request hangs.
2. **A `.then()`/`.catch()` chain inside the handler that doesn't call
   `next(err)` in its `.catch()`** -- e.g. `somePromise.then(result =>
   res.json(result))` with no `.catch()` at all, or a `.catch()` that
   logs the error but doesn't call `next(err)`, leaving the response
   never sent.
3. **An error thrown inside a callback passed to a non-promise-aware
   API** (a raw callback-style DB driver call, a `setTimeout`) inside an
   `async` handler -- throwing inside that inner callback doesn't
   propagate to the outer `async` function's try/catch at all, since it's
   a separate call stack.
4. **A custom `asyncHandler`/wrapper utility that catches errors but
   calls `next()` without the error argument**, or catches errors only
   from the promise returned by the handler and misses errors thrown
   synchronously before the first `await`.

## Diagnose
- Check the Express major version (`package.json` / `node_modules/
  express/package.json`) -- Express 5 automatically forwards rejected
  promises from `async` handlers to `next(err)`; Express 4 and earlier do
  not, and that single fact explains most instances of this symptom.
- Reproduce directly: hit the route with input designed to throw, and
  check whether the process's error-handling middleware (the one with
  the four-argument `(err, req, res, next)` signature) logs anything at
  all. If it's never invoked, the error isn't reaching Express's error
  path, confirming this rather than a formatting bug in the handler
  itself.
- Grep every async route handler for the shape of its error handling:
  handlers with no `try/catch` and no wrapping utility, `.then()` chains
  missing `.catch()`, and any wrapping utility in use -- read that
  utility's implementation directly rather than assuming it's correct,
  since a wrapper that appears to handle errors but calls `next()`
  without an argument produces this exact symptom.
- For an error inside a nested callback, trace whether the throwing code
  is actually inside the `async` function's own execution context or
  inside a separate callback invoked later by some other API -- a
  `try/catch` wrapped around the `async` function's body does not catch
  throws from a callback that API invokes on its own schedule.

## Fix
- On Express 4, wrap every async handler so thrown errors and rejections
  are passed to `next(err)`: either a small reusable wrapper
  (`const wrap = fn => (req, res, next) => Promise.resolve(fn(req, res,
  next)).catch(next)`) applied to every route, or a well-maintained
  library (`express-async-errors`, which patches Express's routing layer
  itself so plain `async` handlers work directly) -- pick one approach
  and apply it consistently across all routes, not ad hoc per file.
- On Express 5, plain `async` handlers that throw or reject are
  automatically forwarded to `next(err)` -- if migrating from 4, this
  wrapper/patch becomes unnecessary, but audit for any handler that
  intentionally called `next(err)` itself, since double-forwarding is
  harmless but worth knowing about during the migration.
- For errors from callback-style APIs called inside an async handler,
  wrap that specific call in a `new Promise((resolve, reject) => {...})`
  so its callback's error can be turned into a rejection the outer
  `async` function (and therefore the wrapper/Express 5) can actually
  catch, or await the API's own Promise-returning variant if one exists.
- Ensure any custom wrapper's `.catch()` calls `next(err)` with the
  actual error, not `next()` with no argument (which tells Express "no
  error, continue to the next middleware" -- the opposite of what's
  intended) and not a bare `console.error(err)` with no `next()` call at
  all.

## Pitfalls
- Adding `express-async-errors` (or an equivalent monkey-patch) fixes
  new code but doesn't retroactively fix handlers that already have a
  broken `.catch()` swallowing the error without calling `next()` --
  audit existing handlers too, don't assume the patch alone closes every
  instance of this symptom.
- A wrapper that only catches the promise returned by the handler misses
  errors thrown synchronously *before* the first `await` in some
  implementations -- prefer `Promise.resolve(fn(...)).catch(next)` over a
  manual `try { await fn(...) } catch...` if the wrapper needs to handle
  both synchronous throws and rejections uniformly.
- Migrating to Express 5 partly (some routes still assume 4's behavior
  and manually call `next(err)` while relying on old workarounds
  elsewhere) can mask this class of bug in testing while leaving
  inconsistent behavior across routes -- audit error handling
  consistently as part of any Express major-version migration, not just
  the parts that changed behavior.

## Verify
Add a route (or reuse an existing one) whose handler deliberately throws,
and confirm the app's centralized error-handling middleware is invoked
and returns the expected error response -- then repeat with a rejected
promise (not just a synchronous throw) and with an error surfaced from a
nested callback, since each exercises a different part of this failure
mode and a fix for one doesn't guarantee the others are covered.
