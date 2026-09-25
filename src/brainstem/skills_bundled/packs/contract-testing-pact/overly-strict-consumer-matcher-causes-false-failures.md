---
name: overly-strict-consumer-matcher-causes-false-failures
description: Provider verification starts failing on a harmless response change because the consumer contract pinned exact literal values instead of type or pattern matchers.
triggers: ["pact verification fails on unrelated field change", "provider verification breaks on harmless response change", "pact matcher too strict false positive", "contract test fails when only a timestamp or id changed"]
permissions: ["READ"]
---

## Symptom

A provider makes a change that shouldn't affect consumers -- reordering
JSON keys, changing a generated ID's format, updating a timestamp,
adding a new optional field, or fixing a typo in an unrelated field --
and suddenly provider verification fails against a consumer's pact. The
failure diff shows the provider's response is functionally correct, but
it doesn't match the contract byte-for-byte because the consumer test
recorded an exact literal value where a flexible matcher should have
been used.

## Likely causes

- **The consumer test asserted on literal example values captured during
  a single test run** (an exact UUID, an exact timestamp, an exact
  array length) instead of using Pact's matchers (`like`, `eachLike`,
  `term`/regex, `integer`, `datetime`) to express "a string shaped like
  this" or "a number," so any different-but-valid value fails.
- **The consumer test asserted on the full response body wholesale**
  (e.g. deep-equal against a fixture object) rather than only the fields
  the consumer actually reads and depends on, so unrelated fields the
  consumer doesn't even use can still break verification.
- **A matcher was applied to the outer object but not recursively into
  nested arrays/objects**, so the top level tolerates variation but an
  array of items still expects an exact count or exact nested values.
- **Copy-pasted contract-generation code from another consumer/endpoint**
  carried over specific matchers or hardcoded values that happened to fit
  the original example but don't generalize to this endpoint's actual
  variability.

## Diagnose

1. Open the failing verification's diff in the Pact Broker (or the CLI
   output) and identify exactly which field triggered the mismatch --
   check whether that field is one the consumer actually consumes, or
   incidental noise.
2. Open the consumer-side pact test that generated the contract and look
   at how that field's expected value was declared -- a literal value
   (string/number typed directly) instead of a matcher function is the
   tell.
3. Check the generated pact JSON file directly (`pacts/*.json`) for a
   `matchingRules` section -- if the field in question has no
   corresponding rule, it's being compared as an exact literal.
4. Ask whether the consumer's actual production code path would break if
   that field's value changed the way the provider changed it -- if not,
   the contract is over-specified relative to what the consumer truly
   requires.

## Fix

Rewrite the consumer pact test to express expectations at the right level
of specificity: use `like(value)` for "any value of this type," `term()`/
regex matchers for values with a specific format (dates, IDs, enums with
known allowed values), and `eachLike()` for arrays where only the shape
of elements matters, not the count or every entry. As a rule of thumb,
only pin an exact literal value when the consumer's actual business logic
branches on that specific value (e.g. a status enum the consumer switches
on) -- everything else should assert type/shape/pattern, matching what
the consumer's code genuinely depends on rather than what happened to be
in the response during the one test run that generated the contract.

## Pitfalls

Don't overcorrect into asserting nothing at all (e.g. `like({})` on a
whole object with no field-level structure) just to stop failures --
that erases the contract's value entirely, since a provider could then
drop required fields without any verification failure. The right target
is "as loose as the consumer's real tolerance, as strict as the
consumer's real dependency" -- if the consumer parses a field as an
integer and does arithmetic on it, matching `integer()` is correct and
sufficient; matching `like(42)` is fine too, but asserting the literal
value `42` forever is not.

## Verify

Regenerate the pact after fixing the matchers, inspect the resulting JSON
to confirm the field in question now has a `matchingRules` entry with the
appropriate type/format matcher instead of appearing as a bare literal,
then re-run provider verification against a response where that field's
value has deliberately changed (different UUID, later timestamp, extra
harmless field) and confirm it now passes while a genuinely wrong type or
missing field still fails.
