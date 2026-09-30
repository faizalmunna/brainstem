---
name: cypress-session-state-leaking-between-tests
description: A Cypress test unexpectedly starts already logged in, or with leftover state from a previous test, because session or cookie data was not properly isolated between tests.
triggers: ["cypress test starts already logged in", "cookies leaking between cypress tests", "cy.session not isolating state", "test order affects cypress login state"]
permissions: ["READ"]
---

## Symptom

A test that should start from a clean, logged-out state instead behaves
as if a user is already authenticated (or has other leftover state from
an earlier test), and the behavior changes depending on what order tests
run in -- a test passes when run alone but fails, or fails differently,
when run as part of the full suite.

## Likely causes

- **`cy.session()` is used to cache login state across tests for speed**,
  but a test that specifically needs to verify logged-out behavior
  doesn't clear or bypass that cached session, so it inherits a previous
  test's authenticated state.
- **Cookies/localStorage are not cleared between tests** because a
  custom `beforeEach` that used to reset them was removed or never
  written, relying on Cypress's older default behavior (which changed
  across versions) rather than explicit resets.
- **A `cy.session()` validation function is too permissive** (doesn't
  actually check that the session is still valid for the specific test's
  needs), so a session cached from one test context gets reused in a
  context it isn't appropriate for.
- **Application-side state persists outside cookies/localStorage** (a
  server-side session store, a database row) that the test's client-side
  cleanup doesn't touch at all, so even a clean browser session still
  interacts with leftover server state from a prior test.

## Diagnose

1. Run the specific failing test in isolation versus as part of the full
   suite and confirm the behavior actually differs -- this confirms
   cross-test state leakage rather than a bug specific to the test itself.
2. Inspect cookies/localStorage/sessionStorage at the start of the
   failing test (via the Cypress command log or an explicit debug log)
   to see what unexpected state is present.
3. Check whether `cy.session()` is in use and read its validation
   function closely -- confirm it actually re-verifies the session is
   appropriate for the current test rather than just checking a cookie
   exists.
4. Check for server-side state (a database seed, a session store) that
   might persist between tests independent of anything client-side, if
   the leaked behavior isn't explained by cookies/localStorage alone.

## Fix

Use `cy.session()` deliberately and explicitly per logical user/role
rather than relying on it implicitly persisting -- give it a real
validation function that checks the session is actually still what the
test expects, and explicitly avoid `cy.session()` (or clear it) for
tests that specifically need to start logged out. Add an explicit
`beforeEach` that clears cookies and browser storage for any test suite
where isolation matters and shouldn't be left to defaults that can change
across Cypress versions. For server-side state leakage, reset the
relevant part of the test database/session store between test files
(e.g. via a task that seeds a known clean state) rather than relying on
client-side cleanup alone to guarantee isolation.

## Pitfalls

Don't disable `cy.session()`/caching entirely just to fix an isolation
bug -- that's a legitimate performance feature (avoiding a real login
flow on every single test) and losing it can make the suite
significantly slower; fix the validation/scoping instead. Also don't
assume clearing client-side cookies/storage is sufficient isolation when
the application has meaningful server-side session state -- verify what
actually needs resetting rather than only fixing the browser-visible
half of the problem.

## Verify

Run the previously-order-dependent test both in isolation and immediately
after the specific other test that was causing the leak, in both orders,
and confirm consistent, correct behavior in the full suite as well as
isolation, not just full suite. Run the whole suite with Cypress's test
randomization/retries (if available) a few times to catch any remaining
order sensitivity.
