---
name: patch-decorator-stacking-argument-order
description: A test using multiple stacked unittest.mock.patch decorators receives mock arguments in the wrong order, causing assertions against the wrong mock object.
triggers: ["multiple patch decorators wrong order", "mock arguments mixed up", "stacked patch decorator confusion", "patch injects mocks in reverse order"]
permissions: ["READ"]
---

## Symptom

A test function decorated with multiple stacked `@mock.patch(...)`
decorators receives its corresponding mock objects as parameters, but
assertions against a specific mock (checking it was called with certain
arguments) fail in a way that suggests the assertion is actually running
against a *different* mock than intended -- as if the parameters got
swapped.

## Likely causes

- **`unittest.mock.patch` decorators apply bottom-up, but inject mock
  arguments into the test function left-to-right in that same bottom-up
  order** -- a common and well-known point of confusion where the
  decorator closest to the function definition corresponds to the
  *first* mock parameter, not the last, and stacking several patches
  without keeping this order straight leads to mismatched parameters.
- **A decorator was added or removed from the stack without updating the
  corresponding parameter list/order**, so a previously correct mapping
  between decorators and parameters silently became wrong after an
  edit.
- **Patches were stacked in an order that doesn't match the visual/
  logical order they're read in**, making it easy for someone reading or
  editing the test later to assume top-to-bottom corresponds to
  left-to-right parameters, which is backwards from the actual behavior.
- **A mix of `@mock.patch` decorators and `pytest` fixtures on the same
  test function** makes the actual full parameter order harder to reason
  about at a glance, increasing the chance of a mismatch during editing.

## Diagnose

1. List the `@mock.patch(...)` decorators on the test function from top
   to bottom, and map them to parameters in *reverse* order (bottom-most
   decorator maps to the first parameter after `self`/fixtures) --
   compare this expected mapping against what the test code's assertions
   assume.
2. Add a distinguishing `.name` or a print statement for each injected
   mock parameter at the start of the test body to directly confirm which
   mock object corresponds to which patched target at runtime.
3. Check recent git history for the test to see if a decorator was
   added/removed/reordered without a corresponding parameter list update.

## Fix

Keep the bottom-up decorator-to-parameter order explicit and correct
whenever stacking `@mock.patch` decorators, and consider adding a
comment next to each decorator noting which parameter position it
corresponds to, specifically because this ordering is easy to get wrong
and easy to silently break during future edits. Where a test needs many
patches, consider using `with mock.patch(...) as mock_x:` context managers
instead of stacked decorators -- context managers make the
target-to-variable mapping explicit and immune to this ordering
confusion, at the cost of some indentation.

## Pitfalls

Don't "fix" a suspected ordering issue by guessing and swapping parameter
names until assertions pass -- verify the actual bottom-up mapping
concretely (via the runtime `.name`/print check) rather than trial and
error, since a coincidentally-passing guess can still be wrong for the
wrong reason. Also, when converting stacked decorators to context
managers for clarity, verify all existing assertions still target the
correct mock, since the refactor itself is an opportunity to
re-introduce the same class of mistake.

## Verify

After fixing (or converting to context managers), confirm each mock's
assertions (`assert_called_with`, call count) actually target the
correct patched dependency by deliberately breaking one specific
dependency's expected call and confirming the corresponding assertion --
and only that one -- fails.
