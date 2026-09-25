---
name: cypress-fixed-wait-instead-of-aliased-request
description: A Cypress test uses a fixed-duration cy.wait(ms) instead of waiting on an aliased network request, making it flaky under variable CI load.
triggers: ["cypress test flaky in ci but passes locally", "cy.wait fixed time flaky", "cypress test needs longer wait in ci", "hardcoded wait time cypress"]
permissions: ["READ"]
---

## Symptom

A Cypress test passes reliably on a developer's local machine but fails
intermittently in CI, especially under higher CI load or when multiple
test jobs run in parallel on shared infrastructure -- inspection of the
test reveals a `cy.wait(1000)`-style fixed-duration wait used as a proxy
for "the network request should be done by now."

## Likely causes

- **A fixed wait duration was chosen based on local network/response
  timing**, which is faster and more consistent than a shared, often more
  loaded, CI environment, so the same duration is no longer sufficient
  under CI conditions.
- **The wait was added to work around a genuine timing issue without
  identifying the actual event to wait on** (a specific network request
  completing, a specific DOM state appearing), so it's fundamentally
  guessing at a duration rather than waiting on a real, observable signal.
- **CI runners have variable, load-dependent performance** (shared runners,
  resource contention from parallel jobs), so any fixed-duration wait is
  inherently unreliable there even if the duration is generous.
- **The underlying request/state change being waited for is itself
  sometimes slower** (a cold-start server, a cache miss) in ways a fixed
  wait can't account for, since it doesn't know when the operation
  actually finishes.

## Diagnose

1. Identify what event the fixed wait is actually trying to wait for --
   a specific network request completing, a specific element appearing,
   an animation finishing -- by examining what happens in the app during
   that time window.
2. Check whether the flaky test's failures correlate with CI load
   (multiple concurrent jobs, a specific time of day, a specific CI
   runner tier) versus being uniformly random, which further confirms a
   load-dependent timing issue rather than a different root cause.
3. Temporarily increase the fixed wait duration significantly and see if
   flakiness disappears -- if it does, this confirms timing is the actual
   issue (as opposed to a different, unrelated flaky-test cause) and
   narrows the fix to properly waiting on the right signal.
4. Check whether the relevant network request is even interceptable
   (same-origin, not blocked by other issues) as a precondition for
   fixing this with `cy.intercept()`/`cy.wait('@alias')`.

## Fix

Replace the fixed-duration wait with an explicit wait on the actual
signal that matters: `cy.intercept()` + `cy.wait('@alias')` for a network
request, or a `.should()` assertion on the specific DOM state that
indicates completion (an element appearing, disappearing, or containing
expected content) -- Cypress's built-in retry-ability on `.should()`
already handles variable timing correctly without needing a duration
guess. This makes the test's actual wait condition explicit and
self-documenting, and removes the CI-load sensitivity entirely, since the
test now waits exactly as long as needed rather than a fixed guess.

## Pitfalls

Don't simply increase the fixed wait's duration as the fix -- it reduces
the flakiness rate without eliminating the underlying issue, and can
still fail under a slow-enough CI run while also needlessly slowing down
every run that would have finished sooner. Also, when switching to
`cy.wait('@alias')`, make sure the intercept is registered before the
action that triggers the request (see the related intercept-timing
skill in this pack) -- swapping one flaky pattern for another
misconfigured one doesn't actually fix anything.

## Verify

Run the test repeatedly under artificially throttled network conditions
(Cypress supports network throttling) and confirm it still passes
reliably, since this simulates the kind of variable timing that CI load
introduces. Run the test in CI itself, ideally in a deliberately loaded/
parallel scenario matching how CI actually runs the full suite, and
confirm no flakiness across multiple runs.
