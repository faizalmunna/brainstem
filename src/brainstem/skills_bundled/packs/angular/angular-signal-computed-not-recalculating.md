---
name: angular-signal-computed-not-recalculating
description: Diagnose a computed signal that keeps returning its original value even after a signal it depends on visibly changes.
triggers: ["computed signal not updating", "signal not recalculating angular", "computed() stale value angular", "signal dependency not tracked"]
permissions: ["READ"]
---

## Symptom
A `computed()` signal keeps showing its original value in the template
even though `console.log(mySignal())` confirms the signal it should
depend on has actually changed -- the computed simply never seems to
notice.

## Likely causes
1. **The computed callback reads the dependency signal conditionally**,
   inside an `if` branch not taken on the run that established tracking
   -- Angular's signal dependency tracking is dynamic, based on exactly
   which signals were read during a given execution, so a branch that
   never ran never registers as a dependency.
2. **The "changed" value is an in-place mutation** (`mySignal().push(x)`
   or a property assignment on the current object) rather than a call to
   `.set()`/`.update()` with a new reference -- signals compare by
   reference (or a custom `equal`) by default, so mutation produces no
   notification at all.
3. **The computed depends on a plain class field or the original
   `BehaviorSubject`/service state**, not the signal itself, after a
   one-time `toSignal()` conversion elsewhere -- updates to the
   underlying source never flow through to what the computed actually
   reads.
4. **A custom `equal` function passed to the source signal** incorrectly
   treats the new and old values as equal (e.g. a shallow-equal that
   can't tell two structurally similar but distinct objects apart),
   suppressing the update before it ever reaches the computed.

## Diagnose
- Log inside the `computed()` callback body itself (not just around the
  call site) to confirm whether it re-executes at all when the source
  changes -- if the body never runs again, this is a dependency-tracking
  problem, not a computation-logic problem.
- Check that every signal read inside the computed happens unconditionally
  on the code path actually exercised, not buried in an untaken branch.
- Inspect the update call site for the source signal: `.set()`/`.update()`
  with a new reference, versus mutating the value returned by calling the
  signal directly.
- If a custom `equal` was passed to `signal()`, log its arguments and
  return value directly to confirm it isn't misreporting old and new as
  equal.

## Fix
- Restructure the computed to read all relevant signals unconditionally
  near the top of the callback, even if only used inside one branch, so
  Angular's tracking captures the dependency regardless of which branch
  the logic takes on a given run.
- Always update signals holding objects or arrays via `.set()`/`.update()`
  with a new reference (spread/copy the previous value) instead of
  mutating in place -- the same reference-identity rule OnPush relies on
  applies to signals.
- When bridging from RxJS, convert with `toSignal(observable$, {
  initialValue })` and have the computed depend on the resulting signal,
  not the original `Subject`/class field, so the signal graph -- not a
  manual subscription living elsewhere -- is what drives recomputation.

## Pitfalls
- Wrapping every value in a signal without fixing how it's updated just
  moves the mutation bug one layer down -- a signal holding an object
  that's still mutated in place reproduces the same staleness the
  computed had, now with an extra layer of indirection to debug through.
- Overriding `equal: () => false` to force recomputation on every `.set()`
  call defeats signals' built-in memoization entirely and can mask the
  real mutation bug while adding unnecessary recomputation everywhere
  else that reads the signal.

## Verify
Add a temporary log at the top of the `computed()` callback, trigger the
source update through the actual UI interaction, and confirm the log
fires with the new value and the template shows the recomputed result
without requiring a manual page reload.
