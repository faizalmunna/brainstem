---
name: playwright-network-mocking
description: Reliably mock/stub network requests in Playwright tests so they're deterministic and fast, without accidentally testing against a stale mock instead of real behavior.
triggers: ["mock api playwright", "stub network request", "test hits real backend", "route.fulfill", "flaky test because of real api call", "test depends on external service"]
permissions: ["READ"]
---

## Symptom
Tests are slow, flaky, or fail in CI specifically because they depend on
a real backend/third-party service being reachable and returning
consistent data -- or, after introducing mocking, tests pass locally
against outdated mock responses while the real API has since changed
shape, and the mismatch isn't caught until it breaks in production.

## Likely causes
1. **Tests hitting a real backend or third-party API directly**, making
   them dependent on that service's availability, latency, and data state
   -- any hiccup in the dependency becomes test flakiness unrelated to the
   code under test.
2. **Mocking implemented by intercepting too broadly** (e.g. mocking all
   requests to a domain) so a request the test didn't anticipate silently
   gets an unintended empty/default response instead of failing loudly.
3. **Hand-rolled mocks that drift from the real API's response shape**
   over time, since nothing checks the mock against reality -- the test
   suite stays green while the real integration silently breaks.
4. **Mocking at the wrong layer** (stubbing an internal function instead
   of the network boundary) for an E2E test, which no longer exercises
   the actual request/response handling code the test was meant to cover.

## Diagnose
- Identify which requests a given test actually depends on and whether
  they're currently mocked or hitting real services.
- For flaky tests, check whether failures correlate with the real
  service's known issues (rate limits, maintenance windows, network
  conditions) rather than the application code.
- For "mock drifted from reality," check whether there's any process
  (contract tests, periodic replay against the real API, schema
  validation) keeping mocked response shapes honest.

## Fix
- Use Playwright's `page.route()` to intercept and fulfill specific
  network requests with controlled responses, scoped as narrowly as
  possible (a specific URL pattern and method) rather than blanket-
  intercepting a whole domain.
- For requests not explicitly mocked in a given test, let unmatched
  requests fail loudly (or assert on the exact set of requests made)
  rather than silently falling through to an unintended default --
  surfaces gaps in mock coverage immediately instead of masking them.
- Keep mock response fixtures close to the real API's actual shape by
  generating them from real recorded responses where practical (record
  once against a real/staging environment, replay in tests), and
  periodically re-validate fixtures against the real API's current
  schema (a contract test or scheduled check) so drift is caught rather
  than silently accumulating.
- Reserve a smaller set of true end-to-end tests (no mocking, hitting a
  real staging environment) specifically to catch the cases mocked tests
  can't -- integration correctness, not UI behavior -- rather than trying
  to make every test both fully isolated and fully realistic.

## Pitfalls
- Mocking the network at the E2E layer for *every* test, including the
  handful meant to verify real integration behavior, removes the only
  tests that would catch an actual breaking API change before it reaches
  production.
- A test that mocks a request but never asserts the request was actually
  made (headers, body, correct URL) can pass even if the application
  stopped calling the API entirely -- assert on the request, not just the
  response handling.

## Verify
Temporarily change the real API's response shape (in a staging/contract-
test context) and confirm the unmocked integration tests fail
appropriately, while the mocked unit/component-level tests remain fast
and unaffected -- confirming the two test layers are actually covering
different things, not duplicating or leaving a gap.
