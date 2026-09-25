---
name: mock-module-leaks-across-test-files
description: A jest.mock or vi.mock defined in one test file appears to still be active in a different, unrelated test file that never mocked that module itself.
triggers: ["jest mock leaking into another test file", "vi.mock affecting unrelated test", "module still mocked in next test file", "jest.resetModules not working", "mock from one file breaking another suite"]
permissions: ["READ"]
---

## Symptom
A test file that never calls `jest.mock()`/`vi.mock()` for a given module
still observes mocked (fake, stubbed, or `undefined`) behavior from that
module -- or, conversely, a manual mock (`__mocks__/`) that one file
customized with `mockImplementation` still has that customization active
when a completely different file imports the same module. The failure
often only reproduces when running the full suite or a specific file
ordering, not when running the affected file alone.

## Likely causes
- **The module registry isn't reset between files/workers**, so a mock
  registered via `jest.mock()`/`vi.mock()` at the top of one file (which
  is hoisted and applies to that module's cache) persists into another
  file executed in the same worker process, when the test runner reuses
  workers across files without isolating the module registry per file.
- **A manual mock in `__mocks__/` is mutated at runtime** (e.g. a test
  calls `someMock.mockImplementation(...)` on a shared mock module
  object) and nothing calls `resetModules`/`restoreAllMocks` to return it
  to its default factory-defined behavior before the next file runs.
- **`vi.mock`/`jest.mock` was placed in a shared setup file** (loaded via
  `setupFiles`/`setupFilesAfterEach`) rather than scoped to the specific
  test file that needs it, so every file in the run inherits the mock
  whether it wants it or not.
- **Test isolation config is misconfigured** -- Jest's `testEnvironment`
  reuse or Vitest's `pool`/`isolate: false` setting intentionally shares
  module state across files for speed, which is fine until a test
  mutates shared mock state and assumes per-file isolation that isn't
  actually configured.

## Diagnose
1. Run only the suspected "leaking" file and only the file that defines
   the mock, together, in that order and the reverse order
   (`jest file-a file-b` vs `jest file-b file-a`) -- if results differ by
   order, this confirms cross-file leakage rather than a bug in either
   file alone.
2. Check the test runner's isolation settings: for Vitest, look for
   `isolate: false` or a shared `pool: 'threads'`/`'forks'` config in
   `vitest.config.ts`; for Jest, check `testEnvironment` reuse and
   whether `resetModules`/`restoreMocks`/`clearMocks` are set globally in
   `jest.config.js`.
3. Search for `jest.mock(`/`vi.mock(` calls inside `setupFiles` or
   `setupFilesAfterEach` rather than inside individual test files --
   global mocks in setup files apply to every file in the run.
4. Add a log at the top of the suspect file printing the mocked module's
   identity (e.g. `console.log(someModule.someFn.toString())` or
   `someModule.someFn._isMockFunction`) to confirm directly whether the
   import resolved to a mock or the real implementation.

## Fix
Scope mocks to the file that needs them (`jest.mock()`/`vi.mock()` calls
inside the specific test file, not a shared setup file, unless the mock
is genuinely meant to apply globally to every test). Set
`resetModules: true` (Jest) or call `vi.resetModules()` in an
`afterEach`/`beforeEach` so each test gets a fresh module registry instead
of a cached one carrying over mock state. For manual mocks that get
runtime-configured per test (`mockImplementation`, `mockReturnValueOnce`),
pair every customization with `restoreAllMocks()`/`resetAllMocks()` in
`afterEach` so the next file (or the next test) starts from the mock's
default, unmodified factory behavior rather than whatever the previous
test last configured.

## Pitfalls
Don't reach for `vi.mock`/`jest.mock` inside a `beforeEach` hook expecting
per-test scoping -- these calls are hoisted to the top of the file by the
transform and calling the mocking API imperatively inside a hook doesn't
give per-test isolation the way `resetModules` does; it just re-runs the
same static hoisted mock. Also don't disable worker/module isolation
(`isolate: false`, shared workers) purely for a speed win without auditing
every test file for mutated shared mock state first -- the speed gain is
real but it silently reintroduces exactly this leakage class of bug.

## Verify
Run the full suite with `--runInBand`/single-threaded and with the normal
parallel/worker configuration, and separately run the previously-leaking
file in isolation -- all three runs should produce identical pass/fail
results and identical mock call counts. Also run the suite twice with
file order reversed (via `--testPathPattern` ordering or a runner's
shuffle/seed option) to confirm no order-dependence remains.
