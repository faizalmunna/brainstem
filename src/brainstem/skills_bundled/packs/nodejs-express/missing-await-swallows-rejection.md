---
name: missing-await-swallows-rejection
description: Diagnose an async function whose try/catch never fires because the awaited call inside it is missing its await keyword.
triggers: ["catch block never runs", "error swallowed silently in async function", "try catch not catching promise rejection", "function returns before async work finishes", "await missing bug"]
permissions: ["READ"]
---

## Symptom
An `async` function wrapped in `try { ... } catch (err) { ... }` is
supposed to handle a failure from an async call inside the `try` block,
but when that call fails, the `catch` block never runs, no error is
logged, and execution continues as if nothing happened -- often
surfacing much later as a downstream effect of the missing work (a
record that should have been updated wasn't, a response that should have
reflected an error instead returned as if successful) rather than as an
obvious crash.

## Likely causes
1. **The async call inside the `try` block is missing `await`** -- e.g.
   `try { saveRecord(data); } catch (err) { ... }` where `saveRecord` is
   an `async` function. Without `await`, `saveRecord(data)` returns a
   promise immediately and the `try` block completes successfully
   whether or not that promise later rejects -- the `catch` block only
   catches synchronous throws and rejections from *awaited* promises
   within its scope, not from a promise merely created and left
   unattended.
2. **`await` is present on the outer call but missing on a nested one**
   -- e.g. an awaited function that itself calls another async function
   without awaiting it and returns before that inner call resolves,
   so the outer `await` only waits for the outer function's own
   synchronous completion, not for the work it kicked off.
3. **A `.map()`/`.forEach()` inside a `try` block populated with async
   callbacks, awaited incorrectly** -- `await
   Promise.all(items.map(item => processItem(item)))` is correct, but
   `items.forEach(async item => await processItem(item))` (missing the
   `Promise.all` wrapper, or using `forEach` at all) means the outer
   `try` doesn't wait for any of the inner calls, so failures from any of
   them become unhandled rejections outside the `try/catch` entirely
   (see `unhandled-promise-rejection-crashes-process`) rather than being
   caught by it.

## Diagnose
- Grep the affected function for every call to a known-`async` function
  inside a `try` block and check each one for a preceding `await` --
  this is a mechanical, line-by-line check, not a guess: if the function
  being called is `async` or returns a `Promise` and there's no `await`
  (or `return`) immediately before the call, the `try/catch` around it
  cannot see its rejection.
- Reproduce directly: force the specific async call to reject (mock it,
  or trigger the real failure condition) and set a breakpoint or log
  statement inside the `catch` block -- if it never fires despite the
  underlying call definitely rejecting (confirm this independently, e.g.
  with a `.catch()` temporarily attached at the call site), that proves
  the `catch` isn't seeing it.
- Check whether the "swallowed" rejection instead surfaces elsewhere as
  an unhandled rejection warning/crash (if nothing else ever attaches a
  handler to that specific promise) -- if so, this is the same missing-
  `await` root cause but manifesting as a process crash rather than
  silent continuation, and both diagnoses point at the same fix.
- Enable a linter rule that catches this mechanically going forward
  (ESLint's `no-floating-promises` from `@typescript-eslint`, or the
  plain-JS equivalent lint rules that flag an unhandled Promise-returning
  expression statement) and run it against the affected file to see if
  it flags the same line independently.

## Fix
- Add the missing `await` (or `return` it, if the function should
  propagate the promise to its own caller) so the rejection actually
  surfaces inside the `try` block's scope where the `catch` can see it:
  `try { await saveRecord(data); } catch (err) { ... }`.
- For a loop of async calls that all need to complete (and have their
  failures caught) before continuing, use `await
  Promise.all(items.map(item => processItem(item)))` inside the
  `try` -- never a bare `.forEach()` with an async callback, since
  `forEach` does not await or collect the promises its callback returns.
- If the intent is genuinely fire-and-forget (the caller shouldn't wait
  for this to finish), don't put it in a `try/catch` that implies it's
  being awaited -- attach `.catch()` directly on the un-awaited call so
  its rejection is still handled, and make the fire-and-forget intent
  explicit in a comment or a named helper, so it doesn't look like a bug
  to the next person reading it.
- Add the lint rule (`no-floating-promises` or equivalent) to CI so this
  class of bug is caught at review time instead of by observing missing
  side effects in production.

## Pitfalls
- Adding `await` to every Promise-returning call site mechanically,
  including genuinely-intentional fire-and-forget calls, can introduce
  new latency by serializing work that was deliberately meant to run in
  the background -- fix the ones that should have been awaited, and
  explicitly `.catch()` (don't await) the ones that shouldn't.
- Wrapping the call in `try/catch` without `await` and then "fixing" it
  by adding a `.then()` instead of `await` still leaves the outer
  function's own `try/catch` unable to see the rejection, since the
  `.then()`'s callback runs independently of the surrounding
  synchronous `try` block's lifetime.
- Turning on `no-floating-promises` for the first time on an existing
  codebase can produce a large number of pre-existing findings at once
  -- triage them by whether the swallowed rejection is actually reachable
  in practice before fixing all of them under time pressure, since some
  fire-and-forget calls may already have equivalent handling elsewhere.

## Verify
Re-run the reproduction from the diagnose step (force the async call to
reject) and confirm the `catch` block now executes with the actual error
object, and that whatever downstream effect was previously silently
skipped (a database write, a response reflecting the error) now happens
correctly or is surfaced as an explicit failure instead of silently
passing.
