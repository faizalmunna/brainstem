---
name: no-exception-assertion-passes-against-anything
description: A test only asserts that calling a function didn't throw an exception, so it continues passing against almost any mutation to the function's actual logic or return value.
triggers: ["test only checks no exception thrown", "assertion does not check return value", "test passes despite wrong output", "weak assertion no exception"]
permissions: ["READ"]
---

## Symptom

A function has a test that runs without failing, and the function's
logic is later changed (by a refactor, a bug, or a deliberate mutation
during mutation testing) to produce a completely different, wrong result
-- yet the same test continues to pass, because it never checked the
actual return value or resulting state in the first place.

## Likely causes

- **A test was written primarily to catch crashes/exceptions** during an
  early development phase, and calling the function with representative
  inputs and confirming "it doesn't throw" was treated as sufficient
  without a follow-up pass to add real assertions on output.
- **The function's return value or side effect is complex to construct an
  expected value for** (a large object, a formatted report), so an
  assertion on the full expected output was skipped in favor of a
  weaker "it ran" check, as a shortcut under time pressure.
- **A test framework's default/implicit behavior treats a function call
  with no explicit assertion as a passing test**, so a test that's
  missing its assertion entirely (not just a weak one) can look
  identical to a deliberately loose no-exception check at a glance.
- **Copy-pasted test boilerplate** from an earlier, genuinely
  exception-focused test (testing that invalid input correctly throws)
  was reused for a different test meant to verify successful-path
  behavior, carrying over the "just check it doesn't throw" pattern
  inappropriately.

## Diagnose

1. Read the test's actual assertions line by line -- confirm whether
   there's a `expect(result).toEqual(...)`-style check on the actual
   return value/state, or only a call with no assertion, or an assertion
   solely about exception behavior.
2. Deliberately break the function's actual logic (change a calculation,
   swap a condition) in a local branch and re-run the test -- if it still
   passes, this concretely proves the assertion gap.
3. Check whether a mutation testing run flags this specific function's
   mutants as consistently surviving despite the function nominally
   having a test.
4. For tests deliberately checking exception-throwing behavior on invalid
   input, confirm that's genuinely the test's intent (a distinct,
   correctly-scoped test) rather than a stand-in for a missing
   success-path assertion.

## Fix

Add a specific assertion on the function's actual return value or
resulting side effect for its success-path tests, constructing the
expected value explicitly even when it's tedious for a complex output --
consider a snapshot-testing approach for genuinely large, complex outputs
where hand-writing the full expected value isn't practical, while still
reviewing the initial snapshot carefully rather than blindly accepting it.
Keep exception-focused tests explicitly scoped to verifying exception-
throwing behavior for invalid input, separate from tests verifying
correct behavior for valid input.

## Pitfalls

Don't overcorrect into asserting on incidental details of a complex
return value that aren't actually meaningful to the function's contract
(exact object key ordering, internal formatting that isn't part of the
documented behavior) -- assert on what actually matters to correctness,
which keeps the test both meaningful and resilient to harmless changes.

## Verify

Re-run the deliberately-broken-logic experiment from the diagnose step
and confirm the strengthened test now fails against it. If mutation
testing is available, confirm the function's mutation score improves
specifically because previously-surviving mutants related to its return
value are now caught.
