---
name: e2e-vs-unit-coverage-boundary
description: Decide what deserves E2E test coverage versus unit/integration coverage, when a test suite has become slow and expensive because everything is tested end-to-end.
triggers: ["too many e2e tests", "test suite too slow", "what to test with e2e vs unit", "testing pyramid", "e2e tests for everything"]
permissions: ["READ"]
---

## Symptom
A test suite is dominated by slow, expensive E2E tests covering logic
that doesn't actually require a full browser+backend to verify (form
validation rules, a pure calculation, a component's conditional
rendering based on props) -- CI takes a long time, failures are harder to
localize (an E2E failure could be caused by dozens of underlying units),
and the team hesitates to add more tests because each one is expensive.

## Likely causes
1. **No established convention for where new tests belong**, so the path
   of least resistance (add another E2E test, since the E2E suite already
   exists and "tests the real thing") becomes the default for everything.
2. **Business logic tested only through the UI** (a discount calculation,
   a permission check) that could be verified directly and much faster
   with a unit test, with the E2E test only incidentally exercising it as
   a side effect of clicking through a flow.
3. **Fear of unit/integration tests "not being real enough"** after being
   burned by mocked tests that passed while the real integration was
   broken -- an understandable reaction, but one that overcorrects into
   testing everything at the most expensive layer instead of fixing the
   specific gap.

## Diagnose
- For a given E2E test, ask what it's actually verifying: a full
  cross-system user journey (worth E2E), or a specific piece of logic/
  rendering behavior that happens to be reachable through that journey
  (better suited to a faster, more targeted test)?
- Count the ratio of E2E to unit/integration tests and compare against
  the actual complexity distribution of the codebase -- a system with
  substantial business logic but almost no unit tests is a strong signal
  of over-reliance on E2E.
- Identify E2E tests whose failures are hard to localize (the test name
  says "checkout flow" but the actual assertion is about a specific
  discount calculation) -- these are candidates to push down.

## Fix
- Reserve E2E tests for **genuine cross-system user journeys**: can a
  user actually sign up, add an item, and complete checkout, end to end,
  through the real UI and real (or realistically staged) backend --
  fewer, broader, and focused on critical paths.
- Push business logic, validation rules, and component rendering
  behavior down to unit tests, which run in milliseconds and fail with a
  precise, localized message pointing at the exact function/component.
- Use integration tests (testing a service/API layer without a full
  browser) for verifying that multiple units correctly compose (e.g. an
  API endpoint's request-to-response behavior) without paying for full
  browser automation.
- If the original motivation was "burned by mocks passing while
  integration was broken," address that specifically with contract tests
  or a smaller number of genuine integration tests (see
  `playwright-network-mocking`'s guidance on keeping a real-integration
  layer), not by moving everything to the slowest, most expensive layer.

## Pitfalls
- Aggressively deleting E2E coverage to "fix" suite speed without first
  confirming the logic it covered has equivalent unit/integration
  coverage can silently remove real regression protection -- migrate
  coverage down before removing the E2E test, don't just delete and hope.
- The right ratio isn't a fixed number (e.g. "70% unit, 20% integration,
  10% E2E" as a rule to force) -- it depends on the actual risk profile of
  the system; use it as a shape to aim for, not a quota to hit
  mechanically.

## Verify
After migrating a piece of logic's coverage from an E2E test down to a
unit test, temporarily reintroduce the original bug that logic was meant
to catch and confirm the new unit test fails -- proving the coverage
actually moved, not just that a slow test was deleted.
