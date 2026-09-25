---
name: high-coverage-percentage-missing-edge-cases
description: Test coverage reports look healthy at ninety percent or higher while error handling, boundary values, and rare branches remain completely untested.
triggers: ["coverage is high but bugs still slip through", "90 percent coverage but still buggy", "istanbul coverage misleading", "line coverage vs branch coverage", "coverage report green but edge cases broken"]
permissions: ["READ"]
---

## Symptom
The coverage report (from `jest --coverage`, `vitest run --coverage`, or
Istanbul/c8 directly) shows a high percentage -- often celebrated as a
quality signal or even enforced as a CI gate -- yet bugs continue to slip
through in error handling, off-by-one boundaries, empty/null inputs, and
rare conditional branches that the number implies should be safe.

## Likely causes
- **Line/statement coverage is tracked instead of branch coverage**, so a
  function with an `if (error) { handleError() } else { handleSuccess() }`
  counts as "covered" the moment any test executes either branch once --
  the error branch can go completely unexercised while the line-coverage
  percentage still reports the file as mostly or fully covered.
- **Tests exercise the happy path repeatedly across many test cases**
  (inflating the percentage through sheer volume of similar tests) while
  never constructing the specific inputs that trigger validation
  failures, empty collections, maximum/minimum boundary values, or
  concurrent/race conditions -- the coverage tool has no concept of
  "important" input, only "was this line executed."
- **Coverage is measured and enforced at the file or repo aggregate
  level**, so a handful of thoroughly-tested simple files can mathematically
  offset one critical, complex, poorly-tested file (e.g. a payment
  calculation or auth check) without the aggregate number revealing the
  imbalance at all.
- **Generated or trivial code (getters/setters, DTOs, barrel re-exports)
  is included in the coverage denominator**, inflating the percentage with
  lines that were never at risk of a real bug in the first place, while
  crowding out visibility into which *meaningful* logic actually lacks
  tests.

## Diagnose
1. Switch the coverage report to show branch coverage specifically
   (`--coverage --coverageReporters=text` shows a `% Branch` column
   distinct from `% Stmts`/`% Lines` in Istanbul-based tooling) and look
   for files where branch coverage is meaningfully lower than line
   coverage -- that gap is exactly the untested-conditional-paths problem.
2. Open the HTML coverage report (`coverage/lcov-report/index.html`) for
   the specific file in question and look for lines highlighted in
   red/yellow inside `catch` blocks, `else` branches, and default
   switch cases specifically -- these are disproportionately likely to be
   the uncovered lines even in "high coverage" files.
3. For a specific critical function, manually enumerate its boundary
   conditions (empty array, single-element array, null/undefined input,
   maximum safe integer, negative numbers, empty string) and check each
   one against the existing test file -- count how many are actually
   asserted on versus assumed to be fine.
4. Check the coverage config for `collectCoverageFrom`/`coveragePathIgnorePatterns`
   to see whether trivial or generated files are inflating the aggregate,
   and separately compute coverage for just the critical business-logic
   directory to see the real number without that padding.

## Fix
Configure and enforce branch coverage thresholds specifically
(`coverageThreshold: { global: { branches: X } }` in Jest, or the
equivalent in `vitest.config.ts`), not just line/statement coverage, since
branch coverage is what actually reveals untested conditional paths. Set
per-directory or per-file thresholds higher for critical logic (payment
calculation, auth checks, data validation) than the repo-wide default, so
one well-tested trivial module can't mathematically compensate for a
poorly-tested critical one. Write tests explicitly targeting the boundary
values and error paths identified during the manual enumeration --
treat "what happens with zero/negative/max/null/malformed input" as a
required checklist for any function handling external or user-controlled
data, independent of what the coverage tool currently reports as
"needed."

## Pitfalls
Don't chase a higher coverage percentage by adding trivial tests for
simple getters, constants, or pass-through functions that were never at
risk -- this raises the number without improving actual bug-catching
ability and can make the metric even more misleading to whoever reads it
next. Also don't treat 100% branch coverage as proof of correctness --
a branch can be "covered" by a test that never actually asserts anything
meaningful about its outcome (see the companion skill on tests that don't
observe rejected promises), so coverage answers "was this code executed,"
never "was this code's behavior verified."

## Verify
Pick the three highest-risk functions in the codebase (payment/auth/data
validation are common candidates) and confirm branch coverage for each is
reported separately and meets a deliberately-set higher threshold than
the repo default; then mutate one boundary condition in each (flip a `>`
to `>=`, remove a null check) and confirm the existing test suite fails --
if it doesn't, coverage was measuring execution, not verification, for
that function, regardless of the percentage shown.
