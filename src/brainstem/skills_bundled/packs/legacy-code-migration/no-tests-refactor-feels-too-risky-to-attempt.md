---
name: no-tests-refactor-feels-too-risky-to-attempt
description: A legacy module has no automated tests, so every proposed refactor is avoided as too risky, and the code accumulates more complexity because nobody will touch it.
triggers: ["legacy code no tests too risky to refactor", "afraid to touch untested code", "no safety net for refactor", "legacy module nobody wants to change"]
permissions: ["READ"]
---

## Symptom

A legacy module has zero automated test coverage, and every proposal to
refactor, clean up, or even carefully modify it gets rejected or avoided
because nobody trusts that a change won't silently break existing
behavior -- resulting in the module continuing to accumulate patches and
complexity precisely because no one will do the deeper cleanup it needs.

## Likely causes

- **The module was written before the team had a testing culture/
  practice**, or was inherited from a previous team/vendor with no test
  suite ever established, and retrofitting tests felt like a separate,
  large project nobody had time to prioritize.
- **The module's design makes it inherently hard to test** (tight
  coupling to global state, hard dependencies on external systems with no
  seam to mock them), so even a team motivated to add tests faces
  significant upfront restructuring just to make testing possible at all.
- **The module's actual behavior includes undocumented quirks that
  downstream consumers may depend on**, so there's genuine uncertainty
  about what "correct" behavior even is -- any test written might
  encode an accidental bug as if it were intended behavior, or might
  "fix" something a consumer relies on.
- **The perceived cost of writing tests before refactoring feels higher
  than the cost of leaving the code alone**, especially under delivery
  pressure, so the safety investment keeps getting deprioritized in favor
  of the next feature.

## Diagnose

1. Confirm the actual current test coverage for the specific module (a
   coverage tool, or manual inspection) to establish the real starting
   point.
2. Identify the module's actual external interface -- what calls into it,
   what it calls out to -- to scope what a characterization test would
   need to exercise and what would need mocking.
3. Sample real production inputs/outputs (logs, monitoring data) for the
   module to understand its actual observed behavior, including any
   undocumented edge cases that a test suite should capture as-is before
   changing anything.
4. Assess whether the module's design has an accessible seam (a place to
   insert a test boundary) or whether testability itself requires a
   preliminary restructuring step.

## Fix

Write characterization tests -- tests that capture and pin down the
module's *actual current* behavior (including any known-imperfect
quirks), not tests asserting what the behavior *should* ideally be --
before attempting any refactor. This gives a concrete safety net: a
refactor that changes behavior in a way the characterization tests catch
is flagged immediately, without requiring the team to first agree on
"correct" behavior for every edge case. Once characterization tests
exist, refactor incrementally, running the tests after each small step
rather than making one large change and hoping. Where the module's design
itself blocks testability, make the smallest possible structural change
needed to introduce a testable seam (extracting a pure function, injecting
a dependency) as a first, low-risk step before larger refactoring.

## Pitfalls

Don't try to write comprehensive, "ideal" tests before touching legacy
code -- that's a much larger upfront investment that reproduces the same
"too much work to start" paralysis; characterization tests specifically
aim for "capture current behavior reliably," which is a smaller, more
achievable goal than "specify correct behavior comprehensively." Also
don't refactor and add tests in the same change -- add characterization
tests first, confirm they pass against the *unchanged* code, then
refactor separately so any test failure during refactoring is
unambiguous evidence of a behavior change.

## Verify

Confirm characterization tests pass against the original, unmodified
code before any refactoring begins. After each refactoring step, confirm
the same tests still pass, and specifically investigate any failure as a
potential behavior change rather than assuming the test itself is simply
outdated.
