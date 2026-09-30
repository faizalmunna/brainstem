---
name: spyon-not-restored-affects-later-tests
description: A jest.spyOn or vi.spyOn call in one test changes a later, unrelated test's behavior because the spy was never restored to the original implementation.
triggers: ["jest.spyOn affecting other tests", "spy still active in next test", "console.error mock leaking into other tests", "vi.spyOn not restored", "restoreAllMocks not called after spyOn"]
permissions: ["READ"]
---

## Symptom
A test later in the same file (or in a file that runs after it in the
same worker) behaves as though a function is still stubbed, silenced, or
returning a canned value from an earlier test's `jest.spyOn`/`vi.spyOn`
call -- most commonly `console.error`/`console.warn` staying suppressed,
or a spied-on method (`Date.now`, a service method, a module export)
still returning the value the earlier test configured with
`mockReturnValue`/`mockImplementation`.

## Likely causes
- **`jest.spyOn(obj, 'method')` is called without a matching
  `mockRestore()`** in `afterEach`, so the spy (which by default still
  wraps the original implementation, but may have been given
  `mockImplementation`) remains attached to the object for the rest of
  the process, since `spyOn` mutates the actual object's property rather
  than creating an isolated copy.
- **`restoreAllMocks`/`resetAllMocks` is configured in `jest.config.js`
  but only resets mocks created via `jest.fn()`/`jest.mock()`, not
  realizing spies need `restoreMocks: true` specifically** to put back the
  original implementation (`resetMocks`/`clearMocks` alone clear call data
  and configured behavior but do not restore the original function on a
  spy).
- **The spy target is a shared/global object** (`console`, `Date`,
  `Math`, a singleton client) rather than something scoped to the module
  under test, so any leftover spy on it is visible to literally every
  other test in the process, not just tests that import the same module.
- **An early test failure or thrown exception skips the `afterEach`
  cleanup** for that specific test (if the cleanup itself isn't
  sufficiently defensive, or is placed after code that can throw),
  leaving the spy in place even though the file did technically declare a
  restore step.

## Diagnose
1. Identify the exact spy by searching the file (and any shared setup
   file) for `spyOn(` and check whether each one has a paired
   `mockRestore()` (or is covered by a `restoreMocks: true` global
   config) -- an unpaired `spyOn` is the first suspect.
2. Run the suspected-affected test alone versus after the test that
   creates the spy, in that order, and confirm the behavior differs --
   this confirms leakage rather than a bug in the affected test's own
   logic.
3. Check `jest.config.js`/`vitest.config.ts` for `restoreMocks`,
   `resetMocks`, and `clearMocks` and confirm which is actually set --
   these are three different behaviors and it's easy to have configured
   the wrong one believing it covers spies.
4. Add a log right before the affected assertion printing whether the
   spied function is still a mock (`jest.isMockFunction(obj.method)`) to
   directly confirm the spy is still attached at that point in execution.

## Fix
Set `restoreMocks: true` in the Jest/Vitest config so every `spyOn`-created
mock automatically reverts to its original implementation after each test,
without relying on every author remembering a manual `mockRestore()` call.
Where a manual restore is still used (e.g. in a project that can't set the
global option), pair it in an `afterEach` in the same `describe` block as
the `spyOn` call, not in a distant top-level hook that's easy to overlook
when adding a new spy elsewhere in the file. For spies on shared globals
specifically (`console`, `Date`), scope the spy's lifetime as tightly as
possible around the specific test that needs it and restore immediately
after that test's assertions, rather than in a suite-wide `beforeAll`,
since the blast radius of a leaked global spy is every other test in the
process, not just the same file.

## Pitfalls
Don't reach for `resetMocks: true` believing it's equivalent to
`restoreMocks: true` -- `resetMocks` clears a spy's configured
implementation and call history but replaces it with a mock that returns
`undefined`, it does not put back the original function, so code that
still expects the real implementation to run (e.g. real `Date.now()`
after a test that spied on it) will now get `undefined` instead of either
the spy's fake value or the real one. Also don't wrap `console.error` in a
spy to "silence expected error logs" without asserting on it and
restoring it immediately -- an un-restored console spy can hide real
error output from a completely unrelated later test that was relying on
seeing console output during debugging.

## Verify
Run the file with `restoreMocks: true` (or the manual restore in place)
and add a test immediately after the spying test that exercises the same
spied-on function/object with no mocking of its own -- confirm it
observes the real, original behavior, not the previous test's configured
mock value.
