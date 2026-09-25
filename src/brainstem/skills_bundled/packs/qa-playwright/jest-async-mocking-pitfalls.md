---
name: jest-async-mocking-pitfalls
description: Diagnose Jest tests with mocked async functions, timers, or modules that pass incorrectly (false positive) or fail mysteriously due to common mocking mistakes.
triggers: ["jest mock not working", "jest fake timers not advancing", "test passes but shouldnt", "jest mock returns undefined", "async test finishes before assertion"]
permissions: ["READ"]
---

## Symptom
One of: a test passes even though the code under test is actually broken
(a false positive caused by a mock silently returning `undefined` instead
of the mocked value); a test involving `setTimeout`/`setInterval` hangs or
doesn't advance as expected with fake timers; or an async test appears to
finish and report success before the async code it's testing has actually
completed.

## Likely causes
1. **`jest.mock()` auto-mocking a module without providing a return value
   for the specific function called**, so the mock silently returns
   `undefined` -- code that handles `undefined` gracefully (or doesn't
   check the result at all) can make the test pass without ever
   exercising the real logic path.
2. **Missing `await`/`return` on an async assertion or a promise-returning
   call inside a test**, so Jest considers the test complete before the
   async operation (and its assertions) actually run -- a rejected
   promise or a failed `expect` inside an un-awaited async callback can
   be silently swallowed.
3. **Using fake timers (`jest.useFakeTimers()`) but not advancing them**
   (`jest.advanceTimersByTime()`/`jest.runAllTimers()`), so
   `setTimeout`/`setInterval` callbacks never fire during the test, or
   advancing them without also flushing microtasks/promises that the
   timer callback triggers.
4. **A mock reset between tests happening at the wrong point** (or not at
   all) -- `jest.clearAllMocks()`/`resetAllMocks()` not called in
   `beforeEach`, letting call counts and mock implementations leak
   between tests and produce misleading pass/fail results depending on
   test order.

## Diagnose
- For a suspiciously-passing test, check whether the mocked function's
  return value was ever explicitly configured (`mockReturnValue`/
  `mockResolvedValue`) for this specific test case, or whether it's
  relying on the auto-mock default (`undefined`).
- For an async test, check whether every promise-returning call that the
  test depends on is `await`ed, and whether the test function itself is
  declared `async` and returns/awaits its final assertion.
- For fake-timer issues, check whether timers are advanced at all after
  being faked, and whether a mix of real promises and fake timers needs
  an explicit microtask flush (e.g. `await Promise.resolve()` or
  `jest.advanceTimersByTimeAsync`) between advancing timers and asserting
  on their effects.
- For mock leakage, check `beforeEach`/`afterEach` for
  `clearAllMocks`/`resetAllMocks`/`restoreAllMocks` and confirm which one
  is actually needed (`resetAllMocks` also clears configured return
  values; `clearAllMocks` only clears call history).

## Fix
- Explicitly configure mock return values relevant to what the test is
  actually verifying (`mockResolvedValue(expectedData)` for an async
  dependency), rather than relying on auto-mock defaults, and assert on
  the mock being called with the expected arguments in addition to
  asserting on the result.
- Make test functions `async` and `await` every promise the test depends
  on, including the final assertion if it's inside a `.then()`/async
  callback rather than directly awaited in the test body.
- When mixing fake timers with promises, use `jest.advanceTimersByTimeAsync`
  (or interleave `await Promise.resolve()` between timer advances) so
  microtasks scheduled by timer callbacks get a chance to run before
  assertions.
- Add `resetAllMocks` (or `clearAllMocks`, chosen deliberately) in
  `beforeEach` so each test starts from a known mock state regardless of
  execution order.

## Pitfalls
- `resetAllMocks` also wipes any `mockImplementation`/`mockReturnValue`
  configured in a shared `beforeAll`/outer setup, which can silently
  break other tests in the same file that relied on that shared
  configuration persisting -- reconfigure per-test what's needed, or use
  `clearAllMocks` if only call-history resetting is actually required.
- Blindly wrapping every assertion in `try/catch` "to make async tests
  more robust" can swallow genuine assertion failures instead of failing
  the test -- let assertion errors propagate; don't catch them.

## Verify
Deliberately break the real implementation the mock stands in for (or
remove the mock temporarily to run against the real dependency in a safe
environment) and confirm the test would actually fail if the mocked
behavior didn't match reality -- a test that can't fail this way was
providing false confidence.
