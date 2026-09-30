---
name: hardcoded-test-data-becomes-invalid-after-rule-change
description: Tests using hardcoded literal values start failing after an unrelated business rule or validation change, because the hardcoded data silently violated the new rule.
triggers: ["hardcoded test data fails after validation change", "test breaks after business rule update", "literal test value no longer valid", "test data violates new constraint"]
permissions: ["READ"]
---

## Symptom

After a seemingly unrelated change to a validation rule or business
constraint (a stricter email format check, a new minimum password
length, a new required date range), several tests across the codebase
start failing -- and the failures trace back to hardcoded literal test
values (a specific email string, a specific date, a specific password)
that happened to satisfy the old rule but not the new one.

## Likely causes

- **Hardcoded literal values were used directly in many tests**
  (`"test@test"`, a specific fixed date string, a short hardcoded
  password) rather than generated through a shared, centrally maintained
  helper that reflects current validation rules.
- **The literal values were valid by coincidence rather than by design**
  -- they happened to satisfy whatever rules existed when the test was
  written, with no explicit connection to the actual validation logic
  that would flag them as still-valid or now-invalid.
- **The same hardcoded value was copy-pasted across many test files**
  rather than defined once, so a rule change that invalidates it breaks
  every copy independently, each requiring the same fix repeated many
  times.
- **No single source of truth exists for "a valid example value" for a
  given field**, so each test author independently guessed at one,
  producing many different hardcoded values with the same fragility.

## Diagnose

1. For each newly failing test, identify the specific hardcoded value
   that now violates the changed rule, and confirm it's a literal
   rather than a generated/factory value.
2. Search the codebase for other occurrences of the same or similar
   hardcoded literal values that might have the same latent fragility
   even if they haven't failed yet (because they aren't currently
   exercised by a code path affected by this particular rule change).
3. Check whether a shared factory/helper for generating valid example
   data for this field already exists but simply wasn't used in the
   failing tests, versus no such helper existing at all.
4. Review the actual validation rule change to fully understand its new
   constraints, to ensure the fix produces genuinely valid data going
   forward, not just data that happens to pass today.

## Fix

Replace hardcoded literal values with calls to a shared, centrally
maintained factory/helper that generates valid example data based on the
current validation rules -- when a rule changes, updating the one helper
fixes every test that uses it, instead of requiring a search-and-replace
across many files. Where a shared helper doesn't yet exist for a given
field type, create one as part of fixing this issue rather than just
patching the specific literal values that failed this time.

## Pitfalls

Don't fix the immediate failures by hardcoding a *new* literal value that
happens to satisfy the new rule -- that just resets the same fragility
for the next rule change instead of addressing the root cause. Also,
when creating a shared helper, make sure it's actually kept in sync with
the real validation logic (ideally by calling into the same validation
code, or being reviewed alongside any changes to it) rather than becoming
its own independent, equally-driftable source of "valid" values.

## Verify

Confirm all previously-failing tests pass after switching to the shared
helper, and confirm the helper itself is exercised by a test that would
catch it drifting out of sync with the real validation rule in the
future (e.g. asserting the helper's output actually passes the real
validation function, not just an assumption that it does).
