---
name: cypress-before-each-async-setup-not-awaited
description: A test's beforeEach setup appears to run but the test body executes before the async setup work has actually completed, causing intermittent failures that look unrelated to setup.
triggers: ["cypress beforeEach not finishing before test", "cypress setup race condition", "before each hook async not awaited", "cypress test starts before fixture loaded"]
permissions: ["READ"]
---

## Symptom

Tests in a spec occasionally fail with errors suggesting some expected
setup state (a logged-in user, seeded data, a specific starting page)
wasn't actually in place, even though a `beforeEach` hook that should
have established that state ran without an explicit error -- and the
failures are intermittent rather than consistent.

## Likely causes

- **The `beforeEach` hook performs an async operation (an API call via
  `cy.request()`, a database seed via a custom task) but doesn't properly
  chain it into Cypress's command queue**, so Cypress considers the hook
  "done" before the operation actually completes, and the test body
  starts concurrently with it.
- **A Promise-returning operation inside `beforeEach` isn't returned or
  awaited**, so Mocha/Cypress's hook-completion detection doesn't know to
  wait for it -- this is easy to miss because Cypress commands are
  already queued/chained automatically, but a raw non-Cypress Promise
  needs to be explicitly handled.
- **A custom Cypress task (`cy.task()`) used for setup has inconsistent
  timing** because the task's own implementation resolves before its
  actual side effect (writing to a test database, for instance) is fully
  committed and visible to subsequent reads.
- **Setup work was split across multiple hooks (`before` and
  `beforeEach`) with an implicit assumption about ordering** that doesn't
  actually hold, especially around one-time setup that later per-test
  hooks assume already fully completed.

## Diagnose

1. Add explicit logging (`cy.log()`) at the start and end of the
   `beforeEach` hook and at the start of the test body, and check the
   actual observed ordering/timing in the Cypress command log across
   several runs -- intermittent reordering confirms the hook isn't
   properly blocking test start.
2. Check whether the `beforeEach` hook's async operation is a native
   Promise/async function not wrapped in a `cy.wrap()` or otherwise
   chained into Cypress's own command queue.
3. For a `cy.task()`-based setup, verify what the task's Node-side
   implementation actually resolves on -- confirm it resolves only after
   the operation (a database write, a file write) is fully durable, not
   just after it's been kicked off.
4. Check for any `before` (one-time) vs `beforeEach` (per-test)
   assumptions about setup ordering that might not hold, particularly in
   parallelized or retried test runs.

## Fix

Ensure every async operation inside a `beforeEach` is properly returned
or chained so Cypress's (and Mocha's) hook-completion detection correctly
waits for it -- for native Promises, `return` the promise (or convert the
operation into a proper Cypress command chain via `cy.wrap()`), and for
Cypress commands themselves, rely on their natural command-queue chaining
rather than manual `async`/`await` mixed with Cypress commands, which can
create subtle ordering bugs. For `cy.task()`-based setup, make sure the
Node-side task implementation's promise only resolves once the underlying
operation (a write, a seed) is fully complete and durable.

## Pitfalls

Don't paper over this by adding a `cy.wait(ms)` after the setup call as a
buffer -- that's the same anti-pattern as fixed-wait flakiness elsewhere
(see this pack's fixed-wait skill) and doesn't guarantee the setup is
actually done, just probably done within that window. Also be careful
mixing native `async`/`await` syntax with Cypress's own command-chaining
model in the same hook -- Cypress commands are not native Promises, and
awaiting them directly (rather than chaining `.then()`) can produce
confusing, inconsistent behavior.

## Verify

Run the affected spec file repeatedly (dozens of times, or with Cypress's
test retries disabled so any residual flakiness is visible rather than
silently retried away) and confirm zero intermittent setup-related
failures. Add an explicit assertion at the very start of the test body
that checks for the exact state the `beforeEach` was supposed to
establish, to make any future regression fail loudly and clearly rather
than manifesting as a confusing downstream failure.
