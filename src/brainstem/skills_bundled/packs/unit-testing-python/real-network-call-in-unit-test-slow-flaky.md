---
name: real-network-call-in-unit-test-slow-flaky
description: A test labeled as a unit test makes a real network or filesystem call without being marked as such, making the suite slow and flaky in CI depending on external availability.
triggers: ["unit test makes real network call", "test suite slow from unmocked http call", "unmarked integration test", "flaky test depends on external service"]
permissions: ["READ"]
---

## Symptom

A test suite runs noticeably slower than its test count would suggest,
and occasionally fails in CI with a timeout or connection error unrelated
to any code change -- tracing the failure to a specific test reveals it
makes a real HTTP request, database connection, or filesystem operation
against something outside the test process's control, despite being
organized alongside and treated as a fast, isolated unit test.

## Likely causes

- **A dependency that should be mocked (an HTTP client, a database
  driver) was never actually mocked in this specific test**, either
  because it was overlooked when the test was written, or because a
  refactor introduced a new external call that wasn't updated to be
  mocked consistently with the rest of the suite.
- **The test was originally written as a genuine integration test** but
  was moved into the unit test directory/suite without adjusting its
  actual behavior or adding the marker/tag that would let CI treat it
  differently (run less often, in a separate stage, with retries).
- **A shared test utility or base class makes a real call as part of its
  setup**, and any test using that utility inherits the real network
  dependency without the individual test author necessarily realizing it.
- **No CI/test convention exists for marking tests that require external
  connectivity** (a `@pytest.mark.integration` or similar), so there's no
  mechanism to separate fast, reliable unit tests from slower, less
  reliable ones that depend on external state.

## Diagnose

1. Profile the test suite's run time per test (`pytest --durations=N`) to
   identify outliers that take dramatically longer than typical unit
   tests, which is often the fastest way to find hidden real network/
   filesystem calls.
2. For a suspiciously slow or intermittently failing test, trace its
   actual execution (adding temporary logging around suspected I/O calls,
   or using a network-call-blocking tool/library for tests to force a
   loud failure if any real call is attempted) to confirm what's actually
   happening.
3. Check whether the test or any shared setup it depends on lacks a mock
   for a dependency that's mocked in comparable, similar tests elsewhere
   in the suite.
4. Check for any existing test marker convention in the project (a
   pytest marker, a directory-based separation) and whether this specific
   test is correctly categorized under it.

## Fix

Mock the external dependency consistently with how similar tests in the
suite already do it, so the test becomes a genuine, fast, isolated unit
test. If the test is intentionally meant to verify real integration
behavior, explicitly mark it as an integration test (a dedicated pytest
marker, a separate test directory/module) so it can be run in an
appropriate CI stage (less frequently, with awareness that its failures
might reflect external service issues rather than code regressions)
rather than being indistinguishable from fast unit tests. Consider adding
a test-suite-wide safeguard (a fixture or plugin that blocks real network
calls by default in the unit test suite, requiring explicit opt-in) to
catch this class of issue automatically going forward.

## Pitfalls

Don't simply delete a genuinely valuable integration test to make the
unit test suite faster -- integration coverage against real external
behavior has real value; the fix is properly categorizing and running it
appropriately, not eliminating it. Also, when adding a network-blocking
safeguard for the unit test suite, make sure genuinely intentional
integration tests are correctly excluded from that safeguard rather than
being broken by it.

## Verify

Re-run the fixed unit test and confirm it no longer performs any real
network/filesystem I/O (using a network-blocking tool to confirm, if
available) and runs in a time comparable to other unit tests. If a
separate integration test was created/kept, confirm it's correctly
excluded from the fast unit test run and only executes in its intended
CI stage.
