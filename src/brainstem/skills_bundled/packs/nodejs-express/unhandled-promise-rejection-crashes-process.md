---
name: unhandled-promise-rejection-crashes-process
description: Diagnose an Express process that exits or restarts under load because a rejected promise in a route handler was never caught.
triggers: ["node process crashed unhandled rejection", "express server keeps restarting", "UnhandledPromiseRejectionWarning", "pm2 restarting constantly", "server dies on bad request"]
permissions: ["READ"]
---

## Symptom
The Node process running an Express app exits unexpectedly (visible as a
restart loop under PM2/systemd/Kubernetes, or a "crash and recover" gap
in uptime monitoring) instead of the offending request simply returning a
500. Logs show `UnhandledPromiseRejectionWarning` or, on newer Node
versions where unhandled rejections are fatal by default, the process
terminates outright with that error printed just before exit.

## Likely causes
1. **A promise created and never returned/awaited inside a route
   handler** -- e.g. calling `sendWelcomeEmail(user)` (which returns a
   promise) without `await` or `.catch()`, so a rejection from it has no
   attached handler anywhere.
2. **An async callback passed to something that doesn't await it**, most
   commonly `setTimeout`, `setInterval`, an event emitter's `.on()`
   listener, or an array method like `.forEach()` given an `async`
   callback -- `forEach` never awaits or checks the return value of its
   callback, so a rejection inside it is unhandled by construction.
3. **A background/fire-and-forget task kicked off from a request**
   (queue a job, write an audit log, invalidate a cache) that isn't
   awaited because the response shouldn't wait on it, but also has no
   `.catch()` attached, so any failure in that fire-and-forget path
   becomes an unhandled rejection instead of a logged, contained failure.
4. **Relying on Express's synchronous error handling for an async
   handler** on Express 4 or earlier -- a thrown error inside an `async`
   function becomes a rejected promise, and pre-Express-5 Express does
   not catch rejections thrown by async handlers on its own (see
   `async-handler-error-not-caught-by-express` for that specific pattern).

## Diagnose
- Confirm it's actually this failure mode: check process logs for
  `UnhandledPromiseRejectionWarning` (or, on Node versions where this is
  fatal, a stack trace immediately preceding process exit) rather than an
  OOM kill or a segfault, which look similar in a restart-loop but have
  different causes.
- Add a top-level `process.on('unhandledRejection', (reason, promise) =>
  {...})` handler (temporarily, for diagnosis, logging the full reason
  and a stack) if one isn't already present -- this turns "which request
  caused it" into an answerable question instead of a silent crash.
- Grep for promise-returning calls that aren't preceded by `await`,
  `return`, or followed by `.catch()` or `.then(_, onRejected)` --
  particularly inside `.forEach()`, `setTimeout`/`setInterval` callbacks,
  and event listener callbacks, since those are the classic places an
  `async` function's rejection has nowhere to go.
- Check the Node version and Express version in use: Node has changed the
  default behavior for unhandled rejections across versions (from a
  warning to a fatal exit), and Express's own async-error-catching
  behavior differs between major versions -- both matter for whether this
  crashes the process or just warns.

## Fix
- Attach a `.catch()` (or wrap in `try/await`) to every promise a route
  handler creates but does not return, especially fire-and-forget
  background work -- the fix isn't to await it (that would block the
  response on work that shouldn't gate it), it's to give the rejection
  somewhere to go: `doBackgroundWork().catch(err => logger.error(err))`.
- Never pass an `async` function directly to `.forEach()`, `setTimeout`,
  or an event emitter's `.on()` without wrapping the body in its own
  `try/catch` -- these call sites don't propagate the returned promise
  anywhere, so any rejection inside must be handled at the point of
  creation, not the point of call.
- For route handlers specifically, wrap async logic so thrown errors and
  rejections are funneled into Express's `next(err)` path (an
  `asyncHandler`/`wrap` utility, or upgrade to Express 5 which does this
  automatically) rather than escaping as unhandled rejections.
- As a last line of defense (not a substitute for the fixes above), keep
  a `process.on('unhandledRejection', ...)` handler in production that
  logs with full context and either lets the process exit cleanly for a
  process manager to restart, or exits deliberately after logging --
  don't leave it as a silent no-op, and don't use it to paper over
  rejections you haven't actually diagnosed.

## Pitfalls
- Adding a global `process.on('unhandledRejection', () => {})` that
  swallows the event with no logging "fixes" the crash but converts a
  loud failure into a silent one -- the underlying bug (a request that
  fails without the caller ever knowing) still exists, it's just hidden
  now.
- Awaiting a fire-and-forget task just to avoid the unhandled rejection
  makes the response latency depend on work the caller doesn't need to
  wait for (e.g. blocking a signup response on a non-critical welcome
  email) -- attach `.catch()` instead of `await` when the work is
  genuinely allowed to happen after the response.
- Relying solely on `process.on('unhandledRejection', ...)` to catch
  every case masks *where* in the code the rejection originated -- fix
  the specific missing `.catch()`/`await` at the call site as the primary
  fix, and treat the process-level handler as a safety net, not the
  mechanism.

## Verify
Trigger the specific code path that previously crashed (e.g. call the
background task with input that makes it reject) and confirm: the
process stays up, the request still returns an appropriate response, and
the rejection is visible in logs with a stack trace pointing at the
actual failing call -- not just an `unhandledRejection` warning with no
route context.
