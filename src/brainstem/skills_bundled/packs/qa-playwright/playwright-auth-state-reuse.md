---
name: playwright-auth-state-reuse
description: Speed up and stabilize a Playwright suite by reusing authenticated session state instead of logging in through the UI in every test.
triggers: ["playwright login every test slow", "storagestate", "auth setup playwright", "test suite slow because of login", "reuse authenticated session playwright"]
permissions: ["READ"]
---

## Symptom
A test suite spends a significant fraction of its total runtime logging
in through the UI (filling a form, waiting for redirects) at the start of
nearly every test, and/or login-related flakiness (a slow auth provider,
an occasional CAPTCHA/MFA prompt in a test environment) shows up across
many unrelated tests instead of being isolated to the login tests
themselves.

## Likely causes
1. **Every test performs a full UI login** as its first step, even though
   almost none of those tests are actually testing the login flow itself
   -- login becomes the slowest, most-repeated, and most flake-prone part
   of the entire suite by sheer repetition.
2. **No shared, reusable authenticated state** across tests, so each test
   re-derives it from scratch via the UI instead of once, ahead of time.
3. **Session/auth state that's tied to a single browser context** rather
   than something exportable and reusable across the many isolated
   contexts Playwright creates per test/worker.

## Diagnose
- Check how many tests perform a UI login as setup versus how many are
  actually testing the login flow itself -- the ratio usually reveals the
  redundancy directly.
- Measure the time spent in login-related steps across a full suite run
  (Playwright's HTML report breaks down step timing) to quantify the
  actual cost before optimizing.

## Fix
- Perform the UI login once (or via a faster API/programmatic login call
  where the app supports it) in a setup project/step, then save the
  resulting session via `context.storageState({ path: ... })`.
- Configure the rest of the test suite (a separate Playwright "project"
  depending on the setup project) to load that saved storage state via
  `use: { storageState: 'path/to/state.json' }`, so every test starts
  already authenticated without repeating the UI flow.
- If the application exposes a direct API endpoint for login/session
  creation (even a test-only one, gated to non-production environments),
  use that instead of the UI for the one-time setup step -- faster and
  removes UI flakiness from the auth step entirely.
- For suites needing multiple distinct roles/permission levels, save a
  separate storage state per role and reference the appropriate one per
  test project/group.

## Pitfalls
- Sharing one authenticated storage state across tests that mutate
  account-level data (changing the user's own settings, deleting their
  own data) can cause cross-test interference if tests run in parallel
  against the same underlying account -- use distinct seeded
  accounts/state per parallel worker for tests that need write isolation,
  not one shared login for everything.
- A saved storage state can go stale if the session has a short expiry
  and the full suite run takes longer than that -- regenerate it as part
  of the suite run (in the setup step, every run) rather than committing
  a long-lived static fixture that silently expires.
- Reusing auth state removes coverage of the login flow itself from every
  other test's path -- keep a small, explicit set of tests that do
  exercise the real UI login, so that flow isn't left completely
  untested.

## Verify
Compare total suite runtime before and after switching to storage-state
reuse, and confirm the dedicated login-flow tests (which still use the
real UI login) still pass -- verifying the optimization didn't
accidentally remove real coverage of the login path itself.
