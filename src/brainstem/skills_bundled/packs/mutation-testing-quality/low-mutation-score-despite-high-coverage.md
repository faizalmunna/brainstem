---
name: low-mutation-score-despite-high-coverage
description: A mutation testing run reports a low percentage of mutants killed even though line and branch coverage for the same code is very high, revealing tests that execute code without asserting on its behavior.
triggers: ["low mutation score high coverage", "mutants survive despite coverage", "mutation testing reveals weak tests", "stryker pit mutmut low score"]
permissions: ["READ"]
---

## Symptom

Running a mutation testing tool (Stryker for JS/TS, PIT for Java, mutmut
for Python) against a module reports a mutation kill score well below
what the module's line/branch coverage percentage would suggest --
many mutants (small, deliberate code alterations) survive because no
test's assertion result changes when the code is subtly broken.

## Likely causes

- **Tests exist and execute the mutated line but assert only on
  something the mutation doesn't affect** (checking a different return
  value, checking only that no exception was thrown), so a mutant that
  changes actual logic still passes every test.
- **Tests assert on internal implementation details** (that a specific
  helper function was called) rather than observable output, so a
  mutation that changes behavior without changing which functions get
  called survives undetected.
- **A mutant is genuinely equivalent** -- the mutation doesn't actually
  change observable behavior for any input the code could realistically
  receive -- and gets miscounted as a "survived" mutant that should be
  killed, when it's actually not a meaningful gap at all.
- **Test data used across many tests shares the same input values**,
  so a mutation affecting behavior only for a different, untested input
  value survives even though the code path is nominally covered.

## Diagnose

1. For each surviving mutant reported by the tool, look at exactly what
   line was mutated and how (e.g. `>` changed to `>=`, a return value
   negated) and identify which existing test executes that line.
2. Check that test's assertions specifically against what the mutation
   changed -- does the assertion depend on the exact behavior the
   mutation altered, or does it check something unaffected?
3. For a suspected equivalent mutant, manually reason through (or test)
   whether any real input could ever produce a different observable
   result between the original and mutated code -- if truly none can,
   it's an equivalent mutant, not a real test gap.
4. Group surviving mutants by root cause (assertion too loose vs.
   genuinely untested input vs. equivalent mutant) rather than treating
   every survivor identically -- they need different responses.

## Fix

For survivors caused by loose assertions, tighten them to check the
actual value/behavior affected by the mutation. For survivors caused by
an untested input value, add a specific test case using that value. For
confirmed equivalent mutants, most mutation testing tools support marking
them as ignored/excluded so they don't continue to muddy the score, but
only after genuinely confirming equivalence, not as a shortcut to
improve the number.

## Pitfalls

Don't chase a 100% mutation-kill-score target mechanically -- some
mutants are genuinely equivalent or represent extremely low-value edge
cases (e.g. mutating a log message string) not worth dedicated test
cases; treat the score as a diagnostic signal pointing at weak spots, not
a target to game by writing narrow tests specifically shaped to kill
individual reported mutants without broader behavioral value.

## Verify

Re-run mutation testing after addressing the genuine (non-equivalent)
survivors and confirm the mutation score improves specifically because
previously-survived mutants are now killed, and spot-check a few newly
tightened tests to confirm they fail against the mutation they were
written to catch, not just that the aggregate score moved.
