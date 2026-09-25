---
name: over-mocked-dependency-hides-integration-bug
description: A unit test suite passes completely green while a real bug in how two modules actually integrate ships to production undetected.
triggers: ["all tests pass but production broke", "mocked everything and missed a real bug", "unit tests green but integration broken", "mock doesn't match real api shape", "tests pass but feature doesn't work"]
permissions: ["READ"]
---

## Symptom
Every unit test passes, coverage looks healthy, and CI is green -- but a
real bug ships where two pieces of code that were each tested in
isolation don't actually work together correctly (a function call with
the wrong argument shape, a response field the caller assumes exists but
the real dependency never returns, an error type the mock never
simulated). The bug is only caught in staging, by QA, or by a user,
never by the test suite that was supposedly covering that code path.

## Likely causes
- **The mock's behavior was written to match what the test *wants* to
  happen, not what the real dependency actually does** -- a mocked
  service method returns a hand-crafted "happy path" object shaped by the
  test author's assumptions, which quietly drifts from the real
  dependency's actual response shape over time (a renamed field, a new
  required parameter, a changed error format).
  <br>See the companion skill for what to do when a mock has *already*
  drifted from reality after a real API change --
  `test-double-mismatched-from-real-api-after-refactor` -- this skill is
  about the broader habit of mocking so much that the seam between two
  real modules is never exercised by any test at all.
- **Every collaborator of the unit under test is mocked**, including
  simple, cheap, deterministic collaborators that didn't need mocking at
  all -- the test then only verifies "this function calls its
  dependencies with these arguments," never that the dependencies'
  actual outputs flow correctly into the function's own logic.
- **There is no test at any level (unit, integration, contract) that
  exercises the real boundary** between the two modules -- unit tests
  mock the boundary on both sides, and nobody added a narrower
  integration test or contract test to cover the seam itself, leaving a
  structural gap in the pyramid rather than a bug in any individual test.
- **Mocks are copy-pasted and reused across many test files** without
  being kept in sync with the real implementation, so a change to the
  real dependency needs to be manually remembered and propagated to every
  mock copy, which reliably doesn't happen consistently.

## Diagnose
1. For the specific bug that shipped, find the unit test(s) that should
   have caught it and check what they actually assert on -- if the
   assertion is "the mock was called with X" rather than "the function
   produced the correct output given a realistic input," that's the
   over-mocking signature.
2. Compare the mock's return shape/behavior directly against the real
   dependency's actual current response (hit the real API in a REPL,
   check its OpenAPI/type definitions, or read its actual source) --
   look specifically for fields, error shapes, or edge cases the mock
   doesn't represent at all.
3. Map the test pyramid for this specific code path: is there anything
   beyond fully-mocked unit tests exercising this integration (a contract
   test, an integration test against a real or realistic test instance,
   an end-to-end test)? If the answer is no at every level, that's the
   structural gap, not a specific test's fault.
4. Check how many test files independently redefine a mock for the same
   dependency -- many independent hand-written mocks of the same real
   thing is a strong signal that at least one of them has drifted from
   reality.

## Fix
Reserve mocking for genuinely expensive, slow, non-deterministic, or
external-system boundaries (network calls, databases, time, randomness),
and let cheap, deterministic, in-process collaborators run for real in
unit tests -- this keeps the test exercising real integration between
most of the call graph while still isolating the actually-expensive edge.
For the boundaries that do need mocking, generate or validate the mock's
shape from a single source of truth (a shared TypeScript type, a
generated client from an OpenAPI/GraphQL schema, a Pact contract) instead
of a hand-written literal, so a real API change either updates the mock
automatically or fails a type/contract check instead of silently
diverging. Add a narrow integration or contract test specifically at the
seam that unit tests mock out, so at least one test in the suite exercises
the real request/response shape between the two systems, even if it runs
less frequently than the unit suite.

## Pitfalls
Don't respond to a shipped integration bug by mocking *less* everywhere
indiscriminately -- replacing all mocks with real calls turns a fast unit
suite into a slow, flaky, network-dependent one and doesn't guarantee the
new real calls are the ones exercising the actual seam that broke. Target
the specific boundary that was under-tested. Also don't treat a contract
test or integration test as optional "nice to have" once unit coverage
looks high -- coverage percentage measures lines executed, not whether
the interaction between two mocked-apart modules was ever verified
against reality.

## Verify
Write (or identify) a contract/integration test for the specific
boundary that caused the shipped bug, run it against the real
dependency's current behavior, and confirm it fails without the fix and
passes with it. Then intentionally break the real dependency's response
shape in a way the old mock wouldn't have caught (rename a field, change
a status code) and confirm the new test catches it while the old
mock-based unit test alone would not have.
