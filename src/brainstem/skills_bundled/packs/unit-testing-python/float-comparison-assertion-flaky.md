---
name: float-comparison-assertion-flaky
description: A test asserting exact equality on a floating-point calculation result fails intermittently or after an unrelated change due to floating-point precision rather than an actual logic bug.
triggers: ["float comparison test flaky", "assertion equal floating point fails", "pytest approx needed", "floating point precision test failure"]
permissions: ["READ"]
---

## Symptom

A test asserting `result == expected_value` on a value derived from
floating-point arithmetic fails intermittently, or starts failing after
an entirely unrelated code change (a different library version, a
different platform/architecture running CI), even though the underlying
calculation logic is correct and the values are "the same" for all
practical purposes.

## Likely causes

- **Floating-point arithmetic is inherently imprecise** for values that
  aren't exactly representable in binary floating point, so a
  calculation that's mathematically equal to an expected value can differ
  in the last few bits of precision depending on the exact order of
  operations performed.
- **A library or Python version change alters low-level floating-point
  operation ordering or implementation** (e.g. a NumPy update changing
  internal summation order), producing a tiny, practically insignificant
  difference that an exact equality check doesn't tolerate.
- **The expected value in the test was itself computed via floating-point
  arithmetic** (rather than being a precise literal), inheriting the same
  precision issues on both sides of the comparison, making the exact
  equality even more fragile than comparing against a fixed literal.
- **Different hardware/platform floating-point behavior** (differences in
  CPU FPU implementation details, though rare with IEEE 754 compliance)
  between a developer's machine and CI produces a different last-bit
  result for the same mathematical operation.

## Diagnose

1. Print the actual computed value and the expected value with full
   floating-point precision (many more decimal places than the default
   display) to see exactly where they diverge.
2. Confirm the difference is at the level of floating-point precision
   (a difference in the 10th+ significant digit) rather than a
   meaningfully different result that would indicate an actual logic bug.
3. Check whether the failure correlates with a library/dependency version
   bump, a different CI runner/OS, or is genuinely nondeterministic run
   to run on the exact same environment.
4. If the expected value was itself computed via floating-point
   arithmetic in the test setup, check whether a fixed, precisely known
   literal could be used instead for a cleaner comparison baseline.

## Fix

Replace exact equality assertions on floating-point results with a
tolerance-based comparison -- `pytest.approx()` for pytest, or an
equivalent tolerance-aware assertion in another framework -- with a
tolerance appropriate to the actual precision requirements of the
calculation (not an arbitrarily loose tolerance that would mask a real
bug). Where practical, use a precisely representable literal (an integer,
or a value chosen to be exactly representable in binary floating point)
as the expected value, avoiding compounding floating-point imprecision
on both sides of the comparison.

## Pitfalls

Don't set the tolerance so loose that it would fail to catch a genuine
logic bug producing a meaningfully wrong result -- choose a tolerance
based on the actual precision the calculation is expected to deliver
(e.g. relative tolerance appropriate to the domain, not a blanket "close
enough" guess). Also don't assume every floating-point comparison issue
is safe to paper over with `approx()` without first confirming the
difference really is precision-level and not an actual behavioral
regression introduced by whatever change triggered the failure.

## Verify

Confirm the test passes reliably across multiple runs and, if the
original trigger was a library/platform difference, confirm it passes on
both the old and new library version/platform with the tolerance-based
assertion in place. Deliberately introduce a real, meaningfully wrong
value in a local branch and confirm the tolerance-based assertion still
correctly fails, proving the tolerance isn't so loose it's lost its
value as a check.
