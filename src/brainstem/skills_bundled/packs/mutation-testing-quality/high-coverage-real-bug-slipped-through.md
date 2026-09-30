---
name: high-coverage-real-bug-slipped-through
description: A module has 100% line and branch coverage, yet a real production bug in that exact module went undetected because the tests execute the code without actually verifying its behavior.
triggers: ["100% coverage but bug in production", "coverage did not catch this bug", "high coverage low quality tests", "tests pass but feature broken"]
permissions: ["READ"]
---

## Symptom

A postmortem for a production bug reveals the affected code has 100%
(or very high) line and branch coverage from existing tests, which
initially seems to contradict the bug's existence -- until closer
inspection shows the tests execute every line but never actually assert
on the specific behavior that was wrong.

## Likely causes

- **Tests were written to satisfy a coverage target** rather than to
  verify specific expected behavior, so they call the code and check only
  that it runs without throwing, not that it produces the correct output
  for the case that later broke.
- **Coverage tools measure execution, not verification** -- a line being
  "covered" only means it ran during some test, with zero information
  about whether any assertion actually checked what that line produced.
- **Boundary and edge-case values were never tested** even though the
  broader code path they run through is covered by tests using typical,
  middle-of-the-road inputs, so an edge case (empty input, a specific
  boundary number, a null) that "counts" as covered by the general test
  was never actually exercised with its own distinct value.
- **A refactor changed behavior in a way tests didn't verify was
  preserved**, because the tests asserted on structure/calls rather than
  observable output, so the refactor kept coverage green while silently
  changing behavior.

## Diagnose

1. Find the test(s) that execute the buggy code path and read exactly
   what they assert -- specifically whether the assertion checks the
   actual value/behavior involved in the bug, or something looser
   (existence, no-exception, a different unrelated property).
2. Manually re-introduce the exact bug that shipped and re-run the
   existing tests -- if they still pass, this concretely proves the
   coverage gap in verification, not just execution.
3. Run a mutation testing tool (Stryker, PIT, mutmut, depending on
   language) against the specific module and check its mutation score,
   not just line coverage -- a low mutation score alongside high line
   coverage is the direct, tool-confirmed signature of this problem.
4. Check whether the specific input/edge case that triggered the bug was
   ever used as a distinct test case, versus only being incidentally
   covered as part of a broader, more generic test.

## Fix

Rewrite the relevant tests to assert on the actual expected output/
behavior for the specific case that broke, not just that the code
executes without error. Adopt mutation testing as a periodic or CI-gated
practice for critical modules specifically because it directly measures
whether tests would catch an introduced bug, which line coverage
structurally cannot measure. Add explicit test cases for boundary/edge
values (empty, zero, negative, max, null) as their own named test cases
rather than assuming a general-case test's coverage extends to them.

## Pitfalls

Don't respond to this finding by chasing a mutation-score target as
mechanically as the original line-coverage target was chased -- writing
tests purely to kill specific reported mutants can produce equally
low-value, brittle tests if done without genuine attention to what
behavior actually matters. Use mutation testing results as a diagnostic
pointing at under-verified code, not as a new number to game.

## Verify

Confirm the rewritten tests fail against the exact reintroduced original
bug (the concrete proof the gap is closed), and confirm the module's
mutation score improves meaningfully on a subsequent mutation testing run,
not just that line coverage stays at 100%.
