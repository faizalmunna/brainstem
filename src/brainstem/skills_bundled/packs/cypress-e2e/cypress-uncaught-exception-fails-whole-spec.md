---
name: cypress-uncaught-exception-fails-whole-spec
description: An unrelated JavaScript error thrown by the application under test fails the entire Cypress spec file instead of just the specific test that triggered it.
triggers: ["cypress uncaught exception failing all tests", "unrelated js error breaks cypress spec", "cypress test fails due to app error not test error"]
permissions: ["READ"]
---

## Symptom

A Cypress spec file has multiple tests, and one uncaught JavaScript
exception thrown by the application under test (not by the test code
itself) during one test causes that test to fail with a confusing
"uncaught exception" error, and depending on when/where the exception
fires, related tests in the same spec can also fail or behave
unpredictably.

## Likely causes

- **The application genuinely has a bug** that throws an uncaught
  exception under conditions the test happens to trigger, and Cypress's
  default behavior is to fail the test when this happens (which is
  usually correct behavior, not a Cypress problem) -- but the failure
  message points at "an uncaught exception" rather than the actual
  assertion the test was checking, making it look like a test-framework
  issue rather than a real app bug.
  by-design behavior surfacing a real app bug, easy to misdiagnose as
  purely a test-tooling annoyance.
- **A third-party script (analytics, ads, a chat widget) embedded in the
  page throws an error unrelated to the feature under test**, and because
  it's unrelated but still uncaught, it still fails the test.
- **An exception is thrown asynchronously after the test's assertions
  already completed** (e.g. from a component unmounting or a stale
  timer), so it fails a test that appeared to have already finished
  successfully, or bleeds into whichever test is running when it
  eventually fires.
- **No `Cypress.on('uncaught:exception')` handling exists to
  intentionally and narrowly ignore known, harmless third-party errors**,
  so every noisy third-party error becomes a test failure regardless of
  relevance.

## Diagnose

1. Read the actual uncaught exception's message/stack trace from the
   Cypress failure output -- confirm whether it originates from
   first-party application code or a third-party script, and whether it's
   plausibly related to the feature the test is exercising.
2. Reproduce the app behavior manually (open devtools, perform the same
   action) to confirm whether the exception is a real, reproducible app
   bug versus something environment-specific to the test run.
3. Check the timing of the exception relative to the test's own
   assertions -- an exception firing well after the test's last assertion
   suggests an async cleanup/unmount issue rather than something the test
   itself directly triggered.
4. If the exception is from a known third-party script, check whether
   it happens outside of Cypress too (in a real browser session) to
   confirm it's a pre-existing, unrelated noise source rather than
   something the test setup introduced.

## Fix

If the exception represents a real application bug, fix the application
bug -- the test correctly caught it, and "cypress fails on uncaught
exceptions" is the intended, useful behavior here, not something to
suppress. For confirmed-harmless, unrelated third-party noise, use
`Cypress.on('uncaught:exception', (err) => {...})` scoped as narrowly as
possible (matching the exact known error message/source, not a blanket
`return false` for all exceptions) so real application errors still fail
tests while specifically known noise doesn't. For async exceptions firing
after a test completes, investigate and fix the underlying cleanup/
unmount issue in the application rather than only suppressing the
resulting Cypress error.

## Pitfalls

Don't add a blanket `Cypress.on('uncaught:exception', () => false)` at
the global config level to make an annoying failure go away -- that
silences every future uncaught exception across the entire suite,
including real application bugs a test would otherwise have correctly
caught, defeating a large part of E2E testing's value. Scope any
suppression as narrowly as the specific known-harmless case, ideally
matching the exact error message.

## Verify

After fixing a genuine app bug, confirm the previously-failing test now
passes without any exception-suppression workaround. After adding a
narrowly-scoped suppression for confirmed third-party noise, deliberately
introduce a new, unrelated real application error in a test environment
and confirm the suite still correctly fails on it -- proving the
suppression didn't accidentally widen to swallow real bugs too.
