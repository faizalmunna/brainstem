---
name: coverage-target-produces-low-value-tests
description: A team optimizing directly for a code coverage percentage target ends up with tests that execute lines without meaningfully verifying behavior, inflating the metric without improving actual quality.
triggers: ["coverage target gaming", "tests written just for coverage", "coverage number high but tests useless", "coverage kpi low value tests"]
permissions: ["READ"]
---

## Symptom

A team has hit or exceeded its mandated code coverage target (e.g. 80%
or 90% line coverage as a CI gate), and the metric trend looks good over
time, but developers privately (or in postmortems) note that many tests
feel like they exist only to satisfy the gate -- calling a function and
asserting little more than "it didn't throw."

## Likely causes

- **Coverage percentage was adopted as a CI-enforced gate without a
  parallel measure of test *quality***, so the path of least resistance
  under time pressure is writing the minimum test that executes a line,
  not the test that best verifies the line's behavior.
- **Code review doesn't scrutinize test assertions the same way it
  scrutinizes production code**, so a shallow test (asserting existence,
  not correctness) passes review as long as the coverage number moves in
  the right direction.
- **Coverage is measured and reported as a single aggregate number**
  without visibility into which specific tests are load-bearing versus
  which are coverage padding, making it hard to even identify where the
  problem is concentrated.
- **New code was written under deadline pressure with coverage treated as
  a checkbox to satisfy before merging**, rather than testing being
  integrated into the design and implementation process itself.

## Diagnose

1. Sample a cross-section of recently added tests specifically written
   to satisfy the coverage gate (identifiable via commit history/PR
   descriptions mentioning coverage) and read their assertions --
   check for the "calls the function, asserts little" pattern directly.
2. Run mutation testing against a sample of high-coverage, low-perceived-
   value modules and compare mutation score against line coverage --
   a wide gap confirms the coverage-gaming pattern with a concrete number.
3. Ask the team directly (in retro or informally) which tests they'd
   trust to actually catch a regression versus which they consider
   "coverage tests" -- developers usually already know the difference
   even if it's never been measured.
4. Check whether code review checklists/guidelines mention test
   assertion quality at all, or only whether tests exist/pass.

## Fix

Introduce mutation testing (even just periodically, or scoped to
critical modules) as a complementary quality signal alongside coverage,
specifically because it measures verification rather than execution --
this gives the team a concrete, harder-to-game number to track alongside
coverage. Update code review practice to explicitly evaluate test
assertion quality (does it check the actual behavior that matters, not
just that code ran) as part of normal review, the same way production
code logic gets reviewed. Consider treating coverage as a floor/sanity
check rather than a target to actively optimize toward -- coverage
dropping is worth investigating, but coverage rising isn't inherently
good news on its own.

## Pitfalls

Don't remove the coverage gate entirely as an overcorrection -- a
coverage floor still catches the case of code with literally zero tests,
which is a real and common failure mode; the fix is adding a
complementary quality signal, not removing the existing one. Also don't
turn mutation testing into a second gameable target with the same
dynamic (see this pack's low-mutation-score skill) -- use it as a review
and investigation tool, not a blunt CI gate applied without human
judgment about equivalent mutants and genuinely low-value edge cases.

## Verify

Track mutation score (even informally, on a sample of modules) alongside
coverage over subsequent development cycles, and check whether newly
written tests -- reviewed under the updated review practice -- would
catch a deliberately reintroduced historical bug, as a periodic spot
check that quality is actually improving, not just the coverage number.
