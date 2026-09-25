---
name: playwright-flaky-test-diagnosis
description: Systematically diagnose a Playwright E2E test that passes and fails intermittently with no code change, rather than guessing at a fix.
triggers: ["flaky test", "test passes locally fails in ci", "intermittent test failure", "test sometimes fails", "playwright flake"]
permissions: ["READ"]
---

## Symptom
A Playwright test fails intermittently -- sometimes passing, sometimes
failing -- with no relevant code change between runs, often more
frequently in CI than locally, or more frequently under parallel
execution than when run alone.

## Likely causes
1. **A race between the test and the app's async state** -- the test
   interacts with an element before the app has finished an async
   operation (a fetch, an animation, a re-render) that the element's
   final state depends on.
2. **An assertion or action that doesn't auto-wait for the actual
   condition** -- e.g. asserting on text content immediately after a
   click without Playwright's built-in retrying assertion, or clicking an
   element that's present in the DOM but not yet interactive (still
   animating, covered by an overlay).
3. **Shared/leaked state between tests** -- a previous test left data in
   the database, local storage, or a shared fixture that the current test
   implicitly depends on being absent, causing failures only when tests
   run in a particular order or in parallel.
4. **Timing sensitive to machine load** -- a fixed `page.waitForTimeout()`
   sized for a fast local machine that's too short under CI's slower/
   more contended environment.
5. **Test-order dependency combined with `.only`/`.skip` left in during
   development**, or genuinely order-dependent tests that only fail when
   parallelized or reordered.

## Diagnose
- Re-run the failing test in isolation, repeatedly (`--repeat-each`), both
  alone and alongside its normal suite, to distinguish "flaky regardless"
  from "flaky only under parallel/ordered execution."
- Use Playwright's trace viewer (`--trace on` or `retain-on-failure`) on a
  failing run to see the exact DOM state, network activity, and console
  output at the moment of failure -- this usually shows directly whether
  the element wasn't ready yet, a request was still in flight, or
  something unexpected was present (an overlay, a stale toast).
- Grep the test for `waitForTimeout` (a fixed sleep) and for assertions
  made via plain reads instead of Playwright's auto-retrying `expect(...)`
  matchers.
- Check `test.describe`/fixture setup for state that persists across
  tests (a shared database, a shared browser context) without being
  reset.

## Fix
- Replace fixed `waitForTimeout` calls with waiting on the actual
  condition: `expect(locator).toBeVisible()`, `page.waitForResponse(...)`
  for a specific network call, or `expect(locator).toHaveText(...)` --
  all of which auto-retry until the condition holds or a real timeout is
  hit, rather than guessing a sleep duration.
- Use auto-retrying `expect` assertions for anything checked after an
  action, not a one-shot read immediately after `click()`.
- Isolate test state: reset/seed the database (or use a fresh, isolated
  fixture) per test rather than relying on ordering or accumulated state
  from previous tests, and avoid sharing a browser context across tests
  that mutate app state.
- If a genuine race exists between the test and a slow async operation
  the app performs, wait on a signal the app actually emits when it's
  done (a specific network response, a DOM attribute the app sets) rather
  than an arbitrary delay.

## Pitfalls
- Increasing a fixed timeout to "fix" flakiness (from 1s to 5s) often
  just makes the test slower without fixing the actual race -- it can
  still fail under a slower CI run or heavier parallel load, just less
  often, which makes the flake harder to notice and reproduce.
- Adding a retry-on-failure at the test-runner level (rerun failed tests
  automatically) hides flakiness from visibility without fixing the root
  cause -- useful as a stopgap for build stability, but track and burn
  down retried tests, don't treat the retry as the fix.

## Verify
Run the fixed test with `--repeat-each=20` (or similar) both in isolation
and as part of the full parallel suite, several times, and confirm zero
failures across all runs -- a single clean run isn't enough evidence for
something that was intermittent.
