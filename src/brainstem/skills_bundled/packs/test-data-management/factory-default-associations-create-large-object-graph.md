---
name: factory-default-associations-create-large-object-graph
description: A test data factory's default associations recursively create a large, unnecessary object graph, slowing down every test that uses it even when the extra data is irrelevant.
triggers: ["factory creates too much data", "test suite slow from factory associations", "factory bot nested associations slow", "test data setup takes too long"]
permissions: ["READ"]
---

## Symptom

The test suite (or a specific subset of tests) runs noticeably slower
than expected, and profiling test setup time shows a large fraction of it
spent creating database records via a test data factory -- often far more
records than the test actually needs or ever references.

## Likely causes

- **A factory's default configuration automatically creates associated
  records** (a `User` factory that also creates a full `Profile`,
  `Address`, and `Preferences` record by default) for convenience, and
  most tests never override this even when they don't need the
  associated data at all.
- **Nested associations compound recursively** -- an `Order` factory
  creating a `User` by default, which itself creates a `Profile` by
  default, and so on -- so a single top-level factory call silently
  creates far more database writes than its name suggests.
- **A factory trait/variant meant for a specific test scenario (full
  realistic object graph) became the default** over time, rather than
  being an explicit opt-in for the tests that actually need that depth.
- **Database writes for associated records use the same expensive
  validation/callback logic as production code paths**, so each
  unnecessary associated record isn't just an extra row but an extra
  full execution of business logic, compounding the cost further.

## Diagnose

1. Profile a slow test's setup phase (most test frameworks/factories
   support logging every database insert during a test) and count how
   many records are actually created versus how many the test's
   assertions actually reference.
2. Trace the factory definition's association chain to identify which
   specific associated factory calls are happening by default versus
   only when explicitly requested.
3. Compare test suite runtime before and after temporarily stubbing out
   a specific expensive default association, to quantify its actual cost
   contribution.
4. Check factory definition history/git blame for when a "convenient
   full object graph" default was introduced, and whether it was
   intended as a universal default or scoped to specific test needs.

## Fix

Make expensive or rarely-needed associations opt-in (via an explicit
trait/parameter) rather than a factory's default behavior, so a plain
factory call creates only the minimal object needed, and tests that
genuinely need a fuller graph explicitly ask for it. For associations
that are usually needed but expensive to create through full application
logic, consider a lighter-weight creation path for test purposes (
bypassing non-essential callbacks/validations that don't matter for the
test's actual purpose) while being careful this doesn't let tests pass
against data shapes real application code could never actually produce.

## Pitfalls

Don't make associations so minimal by default that many tests end up
needing to explicitly request associations they almost always need
anyway -- if the overwhelming majority of tests genuinely need a specific
association, keeping it as a sensible default and making the *exception*
explicit may be the better tradeoff; profile actual usage patterns rather
than assuming "minimal by default" is universally correct.

## Verify

Re-run the test suite (or the specific previously-slow subset) after
scoping expensive associations to opt-in and confirm a measurable
runtime improvement, and confirm the tests that do need the fuller object
graph still pass correctly using the explicit opt-in.
