---
name: unhandled-rejection-silently-passes-test
description: An async test reports success even though a promise it depends on actually rejected or an expected thrown error never happened.
triggers: ["test passes but promise rejects", "expect rejects not working", "async test doesn't catch thrown error", "unhandled promise rejection in jest test", "test green but error was thrown"]
permissions: ["READ"]
---

## Symptom
A test for error-handling behavior (an API call that should reject, a
validation function that should throw) reports as passing, but the code
under test either never actually threw/rejected the way the test assumes,
or it did throw and the test simply never noticed -- sometimes visible
only as an "UnhandledPromiseRejection" warning printed to the console
that nobody looks at because the test itself is green.

## Likely causes
- **A rejected promise inside an async function is awaited without a
  surrounding `try/catch` or a `.catch()`, and the test function itself
  isn't `async`/doesn't return the promise chain**, so the test runner
  considers the test "done" as soon as the synchronous part of the test
  body finishes, before the rejection has actually been observed by
  anything -- the rejection becomes an unhandled rejection logged
  separately, not a test failure.
- **`expect(fn()).rejects.toThrow()` is used but the expectation itself
  isn't awaited or returned** (`expect(promise).rejects.toThrow()` without
  an `await` in front) -- Jest/Vitest schedules the assertion
  asynchronously, and without awaiting it, the test function can complete
  and report success before the assertion has actually run and had a
  chance to fail.
- **The code under test swallows the error internally** (a `catch` block
  that logs and returns `undefined` instead of re-throwing) so there
  genuinely is no rejection to observe by the time the test's assertion
  runs -- this looks identical from the test's perspective to the
  await-ordering bugs above but the actual root cause is in the
  implementation, not the test.
- **A callback-style API is tested with an async/await pattern mismatched
  to it** -- wrapping a callback-based function in a `try/catch` as if it
  were a promise does nothing, because a thrown error inside an
  asynchronous callback doesn't propagate through synchronous
  `try/catch`, so the test's error-catching code never runs at all.

## Diagnose
1. Run the test file with `--detectOpenHandles` (Jest) or check for
   "UnhandledPromiseRejectionWarning"/"unhandled rejection" printed to the
   console during a run that otherwise reports all-green -- this is a
   strong direct signal that a rejection happened but wasn't captured by
   any assertion.
2. Read the specific test body and check every promise-returning
   expression for an `await` or `return` in front of it, including
   `expect(...).rejects...` and `expect(...).resolves...` forms
   specifically, since these are easy to write without the leading
   `await` and still look syntactically complete.
3. Temporarily add `expect.assertions(n)` (Jest) or Vitest's
   `expect.assertions`/`expect.hasAssertions()` at the top of the test
   with the exact expected assertion count -- if the async assertion
   never actually runs due to ordering, the test will now fail with an
   assertion-count mismatch instead of silently passing.
4. Manually call the function under test outside the test framework (a
   quick script or REPL) with the same inputs and confirm, independent of
   the test harness, whether it actually rejects/throws at all -- this
   separates "the implementation doesn't error" from "the test doesn't
   observe the error."

## Fix
Always `await` (or `return`) any promise-based assertion form --
`await expect(promise).rejects.toThrow(SpecificError)` -- rather than
firing it and letting the test function return before it resolves; both
Jest and Vitest require the `await`/`return` for these matchers to
actually gate the test's pass/fail on their outcome. For manually-written
try/catch-based async tests, ensure the test function is declared `async`
and any assertion that a particular line should not be reached (placed
after the call expected to throw) is paired with an explicit
`expect.assertions(n)` (or Vitest's `expect.hasAssertions()`) at the top
of the test, so a code path that skips the catch block entirely fails the
test instead of passing by having simply run zero assertions. For
callback-based APIs, either promisify the function first
(`util.promisify` or a manual wrapper) before testing it with
async/await, or use the test framework's `done` callback pattern
correctly, catching errors inside the callback and passing them to `done`
explicitly rather than relying on an outer `try/catch`.

## Pitfalls
Don't add a blanket top-level `try { ... } catch (e) { }` around an entire
async test body "to prevent unhandled rejections from failing the suite"
-- that suppresses the exact signal (a genuine rejection) the test exists
to detect, converting a real failure into a silent pass. Also don't rely
solely on the test count/coverage report to catch this class of bug --
`expect.assertions(n)` for the specific test is a control that would have
worked and coverage percentage doesn't reveal that an assertion silently
never ran.

## Verify
Add `expect.assertions(n)` with the exact expected count to the fixed
test, then deliberately revert the code under test to not throw/reject
(comment out the throw) and confirm the test now fails loudly with an
assertion-count or matcher mismatch, instead of passing -- this proves
the test can actually detect the absence of the error it's supposed to be
checking for.
