---
name: cypress-retry-masks-real-race-condition
description: A Cypress test passes reliably even though the application briefly showed incorrect state, because command retry-ability kept re-checking until it happened to match.
triggers: ["cypress test passes but app flickers wrong state", "retry-ability hiding a race condition", "cypress assertion eventually passes", "flaky app bug hidden by cypress retries"]
permissions: ["READ"]
---

## Symptom

A Cypress test consistently passes, but manually watching the app run (or
reviewing the Cypress runner's command log/video) shows the UI briefly
displaying wrong or stale data before settling into the correct state --
a real race condition in the application that the test never catches
because Cypress's automatic retry-ability waits until the assertion
happens to pass.

## Likely causes

- **An assertion checks final state only** (`cy.get('.total').should('have.
  text', '42')`) with no check on the intermediate state, so Cypress's
  built-in retrying simply waits out the race condition without ever
  flagging that a wrong value appeared first.
- **The application has a genuine race** between two async operations
  (e.g. two API calls updating the same piece of UI state) where the
  order they resolve in is not actually guaranteed, and the test
  environment's timing happens to make the correct order the common case.
- **A loading/skeleton state is not explicitly asserted on**, so a test
  can't distinguish between "the correct state was there from the start"
  and "the wrong state showed first, then updated" -- both look identical
  to an assertion that only checks the end result.
- **Test environment latency differs from production** (a local/CI test
  environment's API responses may be faster or more consistently ordered
  than production's), so the race window that would be visible under
  real-world network conditions rarely triggers during test runs.

## Diagnose

1. Watch the Cypress test run live (not headless) or review the recorded
   video/screenshots for the exact test, specifically looking for a
   visible flash of incorrect content before the final assertion target
   appears.
2. Add an explicit assertion on the *intermediate* state (e.g. assert the
   loading indicator is shown, or assert a specific wrong value is NOT
   present at any point) rather than only the end state, and see if it
   fails intermittently.
3. Use `cy.intercept()` to artificially delay one of the two racing
   requests by different amounts across repeated runs, and observe
   whether the final rendered state changes based on which one wins --
   this confirms whether a genuine race exists in the app, independent of
   the test.
4. Check application code for the two async operations involved and
   whether they write to shared UI state without any explicit ordering
   guarantee (e.g. no request cancellation for a superseded request).

## Fix

Fix the actual race in the application first (the test masking it is a
symptom, not the root cause) -- typically by canceling/ignoring
out-of-order responses (tracking a request ID or using `AbortController`
so only the latest request's result is applied), or by making the UI
update atomically from a single combined state transition instead of two
independent ones. In the test itself, add explicit assertions on
intermediate/loading states using `cy.intercept()` to control timing
deterministically (delay one request, assert the loading state is shown,
let it resolve, then assert final state) so the test actively exercises
the race window instead of accidentally avoiding it.

## Pitfalls

Don't "fix" the test by adding a `cy.wait(ms)` to dodge the race window --
that just makes the test pass more reliably without checking whether the
underlying race is actually resolved, and can still fail under different
timing (e.g. a slower CI runner). Also don't remove Cypress's retry-
ability to try to "catch" the flash of wrong content -- retry-ability is
what makes most tests reliably non-flaky; the fix is adding assertions
that specifically target the intermediate state, not fighting the
framework's core retry mechanism.

## Verify

Use `cy.intercept()` to deliberately reverse the order the two requests
resolve in (whichever order wasn't originally observed) and confirm the
final UI state is still correct regardless of which request wins --
this proves the race is actually fixed, not just less likely to manifest.
Re-run the test suite a large number of times (or with artificial network
throttling) to confirm no intermittent failures appear.
