---
name: parametrize-silently-skips-cases
description: A pytest.mark.parametrize test silently runs fewer cases than expected because of duplicate test IDs or an exhausted generator passed as the parameter source.
triggers: ["parametrize missing test cases", "pytest parametrize fewer tests than expected", "parametrize generator exhausted", "duplicate test id pytest"]
permissions: ["READ"]
---

## Symptom

A `@pytest.mark.parametrize` test is expected to run once per entry in a
list of test cases, but `pytest --collect-only` (or the actual test run)
shows fewer test instances than the number of cases defined -- some
cases appear to have vanished with no error or warning drawing attention
to it.

## Likely causes

- **Two or more parameter sets produce the same auto-generated test ID**
  (pytest derives IDs from parameter values by default), and pytest
  deduplicates or numbers colliding IDs in a way that's easy to
  misinterpret as cases being dropped rather than just relabeled --
  though in some configurations a genuine ID collision across separate
  `parametrize` stacks can cause confusing collection behavior.
- **The parameter source is a generator or an iterator (not a list/tuple)
  that gets exhausted after being consumed once** -- if it's
  accidentally referenced or iterated over before being passed to
  `parametrize` (e.g. reused across multiple decorators, or evaluated at
  import time and cached), later usages see an empty or partially
  consumed iterator.
- **A parameter list is built dynamically with a bug that produces fewer
  entries than intended** (an off-by-one in a range, a filter condition
  that excludes more cases than expected) -- not a pytest issue at all,
  but easy to misattribute to "parametrize is dropping cases."
- **A test filter (`-k` expression, a marker filter) applied during the
  run unintentionally excludes some parametrized instances**, which looks
  identical to cases being silently skipped by parametrize itself.

## Diagnose

1. Run `pytest --collect-only` on the specific test and count exactly how
   many parametrized instances pytest reports, comparing the printed test
   IDs against the intended parameter list.
2. Print or log the actual parameter list right before it's passed to
   `@pytest.mark.parametrize` to confirm its length and contents match
   what's intended, ruling out a data-generation bug first.
3. Check whether the parameter source is a generator/iterator by type,
   and check whether it's referenced or consumed anywhere else before
   being used in the decorator.
4. Check the exact pytest invocation (including any `-k` filters or CI
   configuration) for anything that might be excluding specific
   parametrized instances.

## Fix

Always pass a concrete, re-usable sequence (a list or tuple, not a bare
generator) to `@pytest.mark.parametrize`, converting explicitly
(`list(my_generator())`) if the source is naturally a generator. Provide
explicit, unique `ids=` for each parameter set when default ID generation
could plausibly collide (e.g. parameter values that stringify to the
same thing), so collection results are unambiguous and each case is
individually addressable. For dynamically built parameter lists, add an
assertion on the list's length immediately before parametrizing, so a
data-generation bug fails loudly at collection time rather than silently
producing fewer test instances.

## Pitfalls

Don't assume `pytest --collect-only`'s reported count is wrong and the
"real" run executes more cases -- collection count is authoritative for
how many test instances will actually run; trust it over an assumption
based on the source list's apparent length. Also, when adding explicit
`ids=`, keep them meaningfully descriptive (not just an index) so a
failure report is still useful for identifying which specific case
failed.

## Verify

Re-run `pytest --collect-only` after the fix and confirm the reported
instance count exactly matches the intended parameter list length, with
each expected case individually visible and distinguishable in the
collected test ID list.
