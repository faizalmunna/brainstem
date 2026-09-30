---
name: fixture-teardown-never-runs-after-error
description: A pytest fixture's yield-based cleanup code never executes because the test raised an exception before the fixture's teardown could run, leaking a resource across subsequent tests.
triggers: ["fixture cleanup not running", "pytest teardown skipped after failure", "resource leaked after test failure", "yield fixture teardown never called"]
permissions: ["READ"]
---

## Symptom

A test that fails (raises an exception or a failed assertion) leaves
behind a resource that a `yield`-based fixture was supposed to clean up
afterward -- a temp file still exists, a database connection stays open,
a mocked global state isn't restored -- and this leaked state then
affects a subsequent, unrelated test in a confusing way.

## Likely causes

- **A misunderstanding of *when* yield-fixture teardown runs** -- pytest
  does run the code after `yield` even if the test fails, but only if the
  fixture setup itself (the code before `yield`) completed successfully;
  if setup fails partway through, the code after `yield` never ran because
  `yield` itself was never reached.
- **The fixture's teardown code itself raises an exception**, which can
  mask the original test failure and also potentially skip later parts of
  the teardown if it's not structured to guarantee full cleanup even when
  part of it fails (no `try`/`finally` within a multi-step teardown).
- **A fixture depends on another fixture whose setup failed**, so neither
  fixture's teardown for that dependency chain runs, and the resource
  leak is actually coming from the fixture chain's setup order, not the
  failing fixture itself.
- **The resource being leaked isn't actually managed by the yield fixture
  at all** -- it was created directly inside the failing test body,
  bypassing the fixture's cleanup responsibility entirely, so the fixture
  was never going to clean it up regardless of teardown timing.

## Diagnose

1. Confirm which fixture is actually responsible for the leaked
   resource, and check whether the resource was created during the
   fixture's setup phase (before `yield`) or directly in the test body.
2. Add explicit logging at the start of the fixture, right at the
   `yield` line, and after `yield` to trace exactly how far execution got
   before or during the failure.
3. If the fixture's setup itself might be failing (not just the test
   body), reproduce that specific failure path and confirm whether
   `yield` is ever reached.
4. Check the teardown code itself for multiple cleanup steps without a
   `try`/`finally` (or equivalent) structure that would let a failure in
   one step still allow subsequent steps to run.

## Fix

Wrap multi-step teardown logic in its own `try`/`finally` (or use
multiple smaller fixtures, each responsible for one resource) so a
failure in cleaning up one resource doesn't prevent cleanup of another.
For resources created directly in a test body rather than in a fixture,
move that resource creation into a proper fixture with its own
yield-based cleanup, so cleanup responsibility doesn't depend on the test
body completing successfully. For fixture chains, ensure each fixture in
the dependency chain manages its own resource's cleanup independently,
so a failure in one doesn't silently skip cleanup for sibling fixtures
that did complete their own setup.

## Pitfalls

Don't add a broad `try`/`except: pass` around fixture teardown code just
to prevent teardown errors from surfacing -- that can hide a real,
separate bug in the cleanup logic itself; instead ensure each cleanup
step's own failure is logged even while allowing other steps to proceed.
Also don't rely on test-order-dependent cleanup (assuming a later test
will "reset" whatever a failed test left behind) as a substitute for
proper fixture teardown.

## Verify

Deliberately make the test body fail (a forced assertion failure) after
the fixture's setup has completed, and confirm the fixture's teardown
code still runs and the resource is properly cleaned up (check the actual
resource state directly -- file no longer exists, connection closed).
Run the previously-affected subsequent test immediately after the
deliberately-failing one and confirm it no longer sees leaked state.
