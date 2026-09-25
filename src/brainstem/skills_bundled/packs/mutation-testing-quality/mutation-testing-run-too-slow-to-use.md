---
name: mutation-testing-run-too-slow-to-use
description: A mutation testing run takes hours to complete because every mutant is tested against the full test suite, making it impractical to run regularly despite its value.
triggers: ["mutation testing too slow", "stryker takes hours", "mutation testing not run in ci", "pit mutmut run time too long"]
permissions: ["READ"]
---

## Symptom

Mutation testing was set up and produced valuable findings once, but it's
not actually run regularly (in CI, or even manually before releases)
because a full run takes hours -- far too slow to fit into normal
development workflows, so the practice quietly lapses after the initial
adoption enthusiasm.

## Likely causes

- **Every mutant is tested against the entire test suite** by default,
  when in reality only the tests that actually exercise the mutated line
  could possibly detect it -- most mutation testing tools can narrow this
  with the right configuration, but it's not always the default.
- **Mutation testing is run against the entire codebase on every
  invocation**, rather than being scoped to only the files/lines changed
  in a given commit or pull request, which is what actually matters for
  day-to-day development feedback.
- **The test suite itself is slow**, and since mutation testing runs
  (a multiple of) the test suite once per surviving mutant candidate,
  any slowness in the base suite gets multiplied dramatically.
- **Mutation testing is run serially** when the tool supports parallel
  execution across multiple processes/machines that wasn't configured.

## Diagnose

1. Check the mutation testing tool's configuration for whether it uses
   coverage data to map each mutant to only the tests that actually
   exercise that line ("coverage-based test filtering" -- most major
   tools support this) versus running the full suite for every mutant.
2. Check whether the tool is configured to run against the whole
   codebase versus a specific, changed subset -- for day-to-day
   development feedback, scoping to a diff is far more practical than a
   full-codebase run every time.
3. Profile how long the base test suite itself takes to run once, and
   multiply by a rough mutant count to sanity-check whether the base
   suite's own speed is the dominant cost.
4. Check whether the tool's parallel execution support is enabled and
   actually using available CPU cores/machines.

## Fix

Enable coverage-based test filtering so each mutant is only tested
against the specific tests that exercise the mutated code, drastically
reducing total run time compared to running the full suite per mutant.
Scope regular mutation testing runs to changed files (in a pull request,
via git diff) rather than the whole codebase, reserving a full-codebase
run for periodic (weekly/monthly) scheduled runs rather than every commit.
Enable parallel execution across available cores, and if the base test
suite itself is slow, treat improving base suite speed as a prerequisite
that pays off across mutation testing and every other CI run.

## Pitfalls

Don't scope mutation testing so narrowly (only the single line changed,
with no surrounding context) that it misses mutants in related code that
the change didn't touch but depends on. Also, don't treat a periodic
full-codebase run as unnecessary once diff-scoped runs are in place --
diff-scoped runs catch regressions in changed code, but a periodic full
run is still valuable for catching drift in test quality across the
whole codebase over time.

## Verify

Measure the actual wall-clock time of a diff-scoped mutation testing run
on a typical pull request and confirm it's fast enough to realistically
run in CI on every PR (or close to it). Confirm coverage-based test
filtering didn't cause any real mutant to be missed by spot-checking that
a deliberately introduced bug in changed code is still caught by the
faster, scoped configuration.
