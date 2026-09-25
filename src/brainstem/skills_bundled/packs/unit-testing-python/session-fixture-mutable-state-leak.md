---
name: session-fixture-mutable-state-leak
description: Diagnose tests that pass alone but fail or see stale data when run together because a session- or module-scoped fixture returns a mutable object shared across tests.
triggers: ["tests fail only when run together", "fixture state leaking between tests", "session scoped fixture pollution", "test pollutes shared fixture", "flaky test depends on order of other tests"]
permissions: ["READ"]
---

## Symptom
A test that assumes it has a clean, private object actually receives a
mutable object (a list, dict, ORM session, in-memory cache, client with
internal state) that a `session`- or `module`-scoped fixture created once
and handed to every test. One test mutates it -- appends to a list, sets a
key, advances a counter -- and a *later* test in the same run sees that
leftover mutation and fails, even though the failing test never touched
the object itself. Running the failing test in isolation, it passes.

## Likely causes
1. **`scope="session"` or `scope="module"` chosen for performance
   (avoiding an expensive setup) without considering that the fixture
   returns a mutable object** -- the scope controls how often the setup
   function runs, not whether the returned object is safe to share; a
   shared dict/list/class instance is shared by reference across every
   test that requests it.
2. **A fixture wraps a client or app object that has internal mutable
   state** (a fake in-memory database, a session object with a
   transaction log, an HTTP client with cookies/auth headers set by a
   previous test) and nothing resets that internal state between tests.
3. **A "reset" step was intended but only runs as part of the fixture's
   teardown, not before each test** -- teardown for a session-scoped
   fixture runs once at the end of the whole session, not between tests,
   so any reset logic placed there never executes between individual
   tests.
4. **Test order happens to hide the bug** in normal runs (alphabetical or
   file-collection order keeps the polluting test after the one it would
   break), so it only surfaces under `pytest-randomly`, a different CI
   worker split, or after an unrelated new test is added earlier in the
   run.

## Diagnose
- Run the suspect test alone (`pytest path::test_name`) and confirm it
  passes in isolation -- this rules out a bug in the test's own logic and
  points at shared state.
- Run the full file or suite with `pytest -p no:randomly` vs. with
  `pytest-randomly` (or `pytest --random-order` / manually reordering two
  tests) to confirm the failure is order-dependent, not flaky for an
  unrelated reason (e.g. real network flakiness).
- Find the fixture chain the failing test depends on with
  `pytest --fixtures test_file.py` or by reading its parameter list, then
  check each fixture's `scope=` argument -- anything above `function`
  scope is a candidate.
- Add a temporary `print(id(fixture_object))` (or log it) at the start of
  each test using that fixture; identical ids across tests confirm the
  same object instance is being reused and mutated.

## Fix
- Default every fixture to `scope="function"` unless there is a measured
  performance reason not to -- function scope gives each test its own
  fresh object with no cross-test coupling to reason about.
- When a broader scope is kept for genuine cost reasons (spinning up a
  real database, a Docker container, an expensive model load), split it
  into two fixtures: an expensive session-scoped "resource" fixture (the
  connection, the container) and a cheap function-scoped fixture that
  resets or wraps that resource per test (starts a transaction and rolls
  it back, clears a cache dict, resets a mock's call history) so each
  test still sees a clean state.
- For ORMs, use the standard pattern of a session-scoped engine plus a
  function-scoped session wrapped in a transaction that's rolled back
  after each test, rather than sharing one long-lived session across
  tests.

## Pitfalls
- "Fixing" this by manually resetting state at the *top* of each test
  body (`shared_list.clear()`) instead of in a fixture works until someone
  adds a new test and forgets the reset line -- the reset belongs in
  fixture setup/teardown, not copy-pasted into test bodies.
- Switching everything to `scope="function"` without addressing why a
  broader scope was chosen can silently reintroduce the slow setup it was
  avoiding (e.g. re-creating a Docker container per test) -- split
  resource creation from state reset instead of just widening or
  narrowing scope uniformly.

## Verify
Run the previously-failing test together with the polluting test in both
orders (`pytest test_a.py::test_b test_a.py::test_a` and the reverse), and
separately run the whole suite under `pytest-randomly` a few times with
different seeds -- all combinations should pass identically.
