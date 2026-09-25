---
name: test-suite-quality-regresses-silently
description: The overall verification quality of a test suite degrades gradually over many changes because mutation score is never tracked or gated the way code coverage typically is.
triggers: ["test quality declining over time", "mutation score not tracked", "test suite got weaker gradually", "no gate on test verification quality"]
permissions: ["READ"]
---

## Symptom

Over many months of development, the codebase's tests still pass and
coverage numbers stay flat or even improve, but the team notices (usually
after a bug that should have been caught wasn't) that tests as a whole
feel less trustworthy than they used to -- more shallow assertions, more
"it ran without throwing" style tests slipping in, with nothing in the
process that would have flagged this drift as it happened.

## Likely causes

- **Coverage is CI-gated and tracked over time, but mutation score (or
  any other verification-quality signal) is not**, so a form of quality
  regression that coverage structurally cannot see has no equivalent
  early-warning system.
- **Individual PRs each look reasonable in isolation** (one slightly
  weak test here, one there), so no single code review catches an
  aggregate trend that's only visible looking at many changes over time.
- **Team composition changed** (new team members without exposure to the
  original testing philosophy/standards) and the previously-implicit
  quality bar for tests was never made explicit enough to onboard new
  contributors into maintaining it.
- **Time pressure on individual features consistently favors the fastest
  test to write** (shallow) over the most valuable one (behavior-
  verifying), and without a counterbalancing metric, this bias compounds
  silently over many decisions.

## Diagnose

1. Run mutation testing against a sample of both old and recently-added
   modules and compare mutation scores -- a measurably lower score in
   newer code versus older code is direct evidence of the drift, not just
   a feeling.
2. Review a sample of recently merged PRs specifically for test
   assertion quality (not just presence) using the diagnostic pattern
   from other skills in this pack (does the assertion check actual
   behavior or just execution).
3. Check whether testing standards/expectations are documented anywhere
   accessible to new contributors, or whether they exist only as
   unwritten team knowledge that erodes as team composition changes.
4. Check historical mutation testing results (if ever run previously) to
   establish a real trend line rather than relying on anecdote alone.

## Fix

Start tracking mutation score (even just for a sample of critical
modules, run periodically rather than on every commit if full coverage
is too slow -- see this pack's runtime skill) as an explicit, visible
metric alongside coverage, so a downward trend is caught the same way a
coverage regression would be. Document the team's actual testing
standards (what makes a good vs. weak assertion, with concrete examples)
so the bar is explicit and transferable to new contributors rather than
tacit knowledge that fades as people join and leave. Include test
assertion quality as an explicit item in code review guidelines, not an
implicit expectation.

## Pitfalls

Don't respond to a detected quality regression by mandating a mutation
score gate on every single PR immediately -- if the base suite is slow,
this can make development painfully slow (see the runtime skill in this
pack); introduce it gradually, scoped appropriately, and paired with
actual time to fix flagged issues rather than as a sudden blocking gate
that generates resentment and workarounds.

## Verify

Track mutation score (or another chosen verification-quality proxy) over
the following several months and confirm it stabilizes or improves
rather than continuing to drift downward. Periodically sample newly
merged PRs against the documented testing standard and confirm adherence
is measurably better than the pre-intervention baseline.
