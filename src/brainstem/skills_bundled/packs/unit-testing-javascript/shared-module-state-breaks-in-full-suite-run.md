---
name: shared-module-state-breaks-in-full-suite-run
description: A test passes reliably when run by itself but fails only when executed as part of the entire test suite, pointing to mutable state shared at module scope.
triggers: ["test passes alone but fails in full suite", "test only fails in CI with other tests", "jest test order dependent failure", "vitest test fails when run together", "module level variable leaking between tests"]
permissions: ["READ"]
---

## Symptom
`npx jest path/to/file.test.js` (or the Vitest equivalent) passes every
time, but `npx jest` (the whole suite) fails that same test intermittently
or consistently -- and the failure is often a wrong count, an
unexpectedly non-empty array/cache, or an assertion about a value that
"should" have been reset. Whichever file happens to run first in a given
worker's execution order is the difference.

## Likely causes
- **A module declares state at the top level** (`let cache = {}`,
  `const seenIds = new Set()`, a counter incremented on each call) instead
  of inside a function/class instance, so every test file that imports
  that module in the same process/worker shares one instance of that
  state for the lifetime of the worker.
- **A singleton pattern (a shared Express app instance, a shared DB client,
  a shared in-memory store) is exported directly from a module** rather
  than constructed fresh per test, so tests that mutate it (add a record,
  register a route, set a header) affect every other test that imports
  the same singleton in the same worker.
- **A test itself mutates an imported object instead of a local copy**
  (`config.debug = true` on a shared config module) and relies on
  `afterEach` to undo it, but the undo is missing, incomplete, or throws
  before it runs, leaving the mutation in place for whichever test runs
  next in that worker.
- **The test runner's worker reuse hides the bug** in small, fast suites
  where files happen to land in separate workers most of the time, so the
  collision only reliably reproduces at a certain suite size or a specific
  CI parallelism setting.

## Diagnose
1. Confirm the isolation vs. real-flake question first: run the full
   suite two or three times and see if the same test fails each time in
   the same way -- consistent failure under the full suite plus consistent
   pass in isolation means shared state, not timing flakiness.
2. Use `--runInBand` (Jest) or a single-worker Vitest config to force all
   files into one process, then bisect by running increasing subsets of
   test files (binary search) until you find the minimal pair of files
   that reproduces the failure together.
3. Once the two files are identified, grep both for top-level
   `let`/`const`/`var` assignments in the modules they both import
   (not in the test files themselves) -- any mutable value declared
   outside a function body in a shared import is a candidate.
4. Add a one-line log of that suspected shared value's identity/content at
   the start and end of each test in both files
   (`console.log(JSON.stringify(sharedThing))`) to directly observe the
   leak happening between them.

## Fix
Move mutable state out of module scope and into something constructed
fresh per test: a factory function that returns a new object/instance
per call, instantiated in `beforeEach`, rather than a module-level
`let`/singleton export. Where a genuine singleton is required by the
production code's design (a connection pool, a registered global), give
tests an explicit reset/teardown hook for it
(`resetForTests()`/`clearAll()`) and call that reset in `beforeEach` or
`afterEach` for every test file that touches it, not just the one that
happened to introduce the mutation. Prefer dependency injection (passing
the store/client into the code under test) over importing a shared
instance directly, so each test can supply its own isolated instance
without needing to know about the module's internal state at all.

## Pitfalls
Don't "fix" this by forcing `--runInBand`/single-worker execution in CI
to avoid triggering the collision -- that just makes the suite slower
while leaving the actual shared-mutable-state bug in the production
module (which can bite in production the same way it bites in tests,
e.g. a memory-resident cache growing unbounded across requests in a
single Node process). Also don't reset shared state only in the test file
that happens to be causing visible failures right now -- the same
module can leak into a different, not-yet-written test file next time
someone adds one, so the reset belongs at the module/fixture level, not
patched into one test file.

## Verify
Run the full suite with the previously-conflicting file pair in both
possible import/execution orders, and run the entire suite several times
in a row (or with the test runner's shuffle/seed option, if available)
to confirm the specific test passes consistently regardless of order or
which other files ran before it in the same worker.
