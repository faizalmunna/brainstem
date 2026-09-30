---
name: cypress-loose-assertion-hides-real-bug
description: A Cypress test passes because it only checks that an element exists or contains some text, missing a real regression in the specific value or state that changed.
triggers: ["cypress test passed but bug shipped", "assertion too loose cypress", "cypress checking existence not value", "regression not caught by passing test"]
permissions: ["READ"]
---

## Symptom

A real regression makes it to production (a wrong total is displayed, a
status shows the wrong value, a list shows duplicate or missing items)
despite an existing Cypress test for that exact feature having passed --
reviewing the test afterward shows it asserted something true but not
specific enough to catch the actual bug (e.g. `cy.get('.total').should
('exist')` instead of checking the actual displayed value).

## Likely causes

- **An assertion checks presence/existence** (`.should('exist')`,
  `.should('be.visible')`) where the test's actual intent was to verify a
  specific value or count, so any content at all satisfies the assertion.
- **An assertion checks a substring/partial match**
  (`.should('contain', 'Total')`) where a more precise match against the
  full expected value would have caught a wrong number appended after the
  matched substring.
- **Automatic retry-ability combined with a loose assertion masks a
  transient wrong value**, similar to the race-condition-masking pattern
  in this pack, but here the looseness is in what's being checked rather
  than timing.
- **The test was written to make a specific historical bug pass, without
  being generalized to catch the broader class of bug** it was originally
  meant to guard against, so a related-but-different regression slips
  through the same gap.

## Diagnose

1. For the specific bug that shipped, find the test that should have
   caught it and read exactly what it asserts -- compare the assertion's
   actual specificity against what would have been needed to catch this
   exact regression.
2. Deliberately reintroduce the shipped bug locally and re-run the
   existing test to confirm it does, in fact, still pass -- this proves
   the assertion gap concretely rather than assuming it from reading the
   code.
3. Check whether the assertion's looseness was intentional (a genuinely
   dynamic value that can't be pinned to an exact match) or just an
   oversight from writing the test quickly.
4. Look for a broader pattern across the test suite of existence/
   substring checks where a precise value check would be equally easy to
   write and meaningfully more protective.

## Fix

Tighten the assertion to check the actual value/state that matters for
the feature's correctness -- an exact text match, a specific count, a
specific computed value -- rather than mere presence, wherever the
underlying value is deterministic enough to assert precisely. For
genuinely dynamic values (a timestamp, a generated ID), assert on a
pattern/format and on the surrounding deterministic context (e.g. that a
computed total based on known seeded input data equals a specific
expected number) rather than giving up and checking only for existence.

## Pitfalls

Don't over-tighten assertions to the point they become brittle to
harmless changes (asserting on exact whitespace/formatting that isn't
actually meaningful to the feature, or hardcoding a value that's expected
to change often) -- the goal is precision on what actually matters, not
maximum strictness on everything. Balance this by asserting on the
specific piece of state relevant to the test's purpose, and using
flexible matchers (regex, numeric comparison) for the parts that are
allowed to vary.

## Verify

After tightening the assertion, reintroduce the original shipped bug
again and confirm the test now actually fails -- this is the concrete
proof the fix closes the gap, not just that the test still passes on
correct behavior. Also confirm the tightened assertion doesn't produce
false failures against legitimate, unrelated changes (e.g. a cosmetic
copy change that doesn't affect the value being checked).
