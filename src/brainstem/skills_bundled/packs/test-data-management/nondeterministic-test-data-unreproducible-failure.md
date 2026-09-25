---
name: nondeterministic-test-data-unreproducible-failure
description: A test fails intermittently and cannot be reproduced reliably because the test data it uses is generated randomly without a fixed, logged seed.
triggers: ["cannot reproduce failing test", "random test data no seed", "flaky test unreproducible", "test data changes every run"]
permissions: ["READ"]
---

## Symptom

A test fails in CI, but re-running it (or trying to reproduce it locally)
produces different, non-matching data and the failure doesn't recur --
making it impossible to confidently debug or confirm a fix, since there's
no way to get back to the exact input that caused the original failure.

## Likely causes

- **Test data generation uses randomness (`Math.random()`, a random
  library call) with no fixed or logged seed**, so every run produces
  different values, and a failure caused by one particular random value
  can't be reconstructed afterward.
- **A property-based/fuzz-testing tool found a failing case but its seed
  or the specific failing input wasn't captured/logged** in the test
  output, losing the exact reproduction case even though the tool itself
  may have internally used a seed.
- **Randomized test data occasionally produces an edge case** (an empty
  string, a boundary number, a specific character encoding) that the code
  under test doesn't handle, but without the exact value, the specific
  edge case triggering it remains unknown.
- **Test infrastructure doesn't surface enough context in failure
  reports** (the actual generated input value, a seed) for the failure to
  be reproducible from the report alone, even if the underlying data
  generation *could* be made deterministic.

## Diagnose

1. Check the failing test's data generation code for whether it uses a
   fixed seed, an environment-provided seed, or unseeded randomness.
2. Check whether the test framework or property-based testing library in
   use has built-in seed logging/reproduction support that simply isn't
   being surfaced in CI output or being used to reproduce the failure.
3. Review the CI failure output itself for whether the actual generated
   input value was logged anywhere, even without a formal seed mechanism.
4. If a specific edge case is suspected, try running the test repeatedly
   with a wide range of manually chosen edge-case values to see if any
   reproduces a similar failure, as a fallback when the original seed is
   genuinely lost.

## Fix

Use a seeded random number generator for test data generation, and log
the seed used for every test run (especially on failure) so any failure
can be exactly reproduced by re-running with the same seed. For
property-based/fuzz-testing tools, ensure the tool's own seed/shrinking
output is captured and surfaced prominently in CI failure output, not
buried in verbose logs that get discarded. Going forward, treat "can this
failure be exactly reproduced from the CI output alone" as a requirement
for any test that uses generated/randomized data.

## Pitfalls

Don't remove randomized/property-based testing entirely in favor of only
hardcoded examples as an overreaction -- randomized testing is valuable
precisely because it explores input space a human wouldn't think to test
manually; the fix is making it reproducible, not eliminating it. Also
don't hardcode a single fixed seed permanently for all runs, since that
defeats the exploratory value of randomization across many runs over time
-- vary the seed by default, but always log it, and support an explicit
override to re-run a specific known seed.

## Verify

Deliberately trigger a test failure (or use a previously logged failing
seed) and confirm it can be reliably reproduced locally using the logged
seed. Confirm CI failure output for randomized tests now includes enough
information (the seed, the actual generated value) for a developer to
reproduce the failure without needing to add ad hoc debugging first.
